import cv2
import itertools
import logging
import math
import numpy as np
import random
import time

from functools import partial
from pathfinding.finder.a_star import AStarFinder
from typing import Generator

from botting import PARENT_LOG
from botting.core.controls import controller
from royals.models_implementations.royals_data import RoyalsData
from royals.bot_implementations.actions.movements import jump_on_rope
from royals.models_implementations.mechanics import (
    MinimapPathingMechanics,
    MinimapNode,
    MinimapConnection,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

DEBUG = True


def random_rotation(data: RoyalsData) -> Generator:
    while True:
        err_count = 0
        target_pos = data.current_minimap.random_point()
        current_pos = data.current_minimap_position

        while math.dist(current_pos, target_pos) > 2:
            data.update("current_minimap_position")
            current_pos = data.current_minimap_position
            actions = get_to_target(current_pos, target_pos, data.current_minimap)
            try:
                first_action = actions[0]
                assert (
                    first_action.args == tuple()
                )  # Ensures arguments are keywords-only
                args = (
                    data.handle,
                    data.ign,
                    first_action.keywords.get("direction", data.current_direction),
                )
                kwargs = getattr(first_action, "keywords", {})
                kwargs.pop("direction", None)
                err_count = 0
                yield partial(first_action.func, *args, **kwargs)
            except IndexError:
                if err_count > 10:
                    logger.error("Could not understand where the fk we are")
                    raise RuntimeError("Unable to understand where the fk we are")
                elif err_count > 2:
                    direction = random.choice(["left", "right"])
                    yield partial(controller.move, data.handle, data.ign, direction, duration=1, jump=True)
                    time.sleep(1)

                if not data.current_minimap.grid.node(*current_pos).walkable:
                    err_count += 1
                    time.sleep(1)



def _debug(
    in_game_minimap: MinimapPathingMechanics,
    start: MinimapNode,
    end: MinimapNode,
    path: list[MinimapNode],
) -> None:
    canvas = np.zeros(
        (in_game_minimap.map_area_height, in_game_minimap.map_area_width),
        dtype=np.uint8,
    )
    canvas = in_game_minimap._preprocess_img(canvas)
    path_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    cv2.drawMarker(
        path_img, (start.x, start.y), (0, 0, 255), cv2.MARKER_CROSS, markerSize=3
    )
    cv2.drawMarker(
        path_img, (end.x, end.y), (255, 0, 0), cv2.MARKER_CROSS, markerSize=3
    )
    for node in path:
        path_img[node.y, node.x] = (0, 255, 0)
    path_img = cv2.resize(path_img, None, fx=5, fy=5)
    cv2.imshow("_DEBUG_ Mode - PathFinding", path_img)
    cv2.waitKey(1)


def get_to_target(
    current: tuple[int, int],
    target: tuple[int, int],
    in_game_minimap: MinimapPathingMechanics,
) -> list[partial]:
    """
    Computes the path from current to target using map features.
    Translates this path into movements, and converts those movements into in-game actions.
    Returns a list of partial objects. However, these partial objects may still require additional args/kwargs.
    :param current: Current minimap position.
    :param target: Target minimap position.
    :param in_game_minimap: The current minimap in-game.
    :return: List of incomplete partial objects that require further args/kwargs.
    """
    path = _get_path_to_target(current, target, in_game_minimap)
    movements = _translate_path_into_movements(path)
    if movements:
        if movements[0] == ('down', 1) and not in_game_minimap.grid.node(*current).walkable:
            movements.pop(0)
    return _convert_movements_to_actions(movements, in_game_minimap.minimap_speed)


def _get_path_to_target(
    current: tuple[int, int],
    target: tuple[int, int],
    in_game_minimap: MinimapPathingMechanics,
) -> list[MinimapNode]:
    """
    Computes the path from current to target using map features.

    :param current: Character position on minimap.
    :param target: Target position on minimap.
    :param in_game_minimap: Minimap implementation which contains minimap coordinates for all existing features.
    :return: A series of MinimapNodes that consist of the path to take to reach target.
    """
    grid = in_game_minimap.grid
    start = grid.node(int(current[0]), int(current[1]))
    end = grid.node(target[0], target[1])
    finder = AStarFinder()
    path, runs = finder.find_path(start, end, grid)
    grid.cleanup()

    if DEBUG:
        _debug(in_game_minimap, start, end, path)
    return path


def _translate_path_into_movements(path: list[MinimapNode]) -> list[tuple[str, int]]:
    """
    Translates a path into a series of movements. Each movement is represented by a tuple of two items.
    The first item is a str representing the actual movement.
    The second item is an int representing the number of nodes to walk through.
    :param path: List of MinimapNodes representing the path to take.
    :return: List of ("movement to do", "number of nodes to walk through") tuples.
    """

    # We start by translating the path into a series of "movements" (up, down, left, right, jump, teleport, etc.).
    movements = []
    for i in range(len(path) - 1):
        current_node = path[i]
        next_node = path[i + 1]
        dx = next_node.x - current_node.x
        dy = next_node.y - current_node.y

        # Cases when there's only 1 unit of displacement - Simply walk in that direction
        if dx == 1 and dy == 0:
            movements.append("right")
        elif dx == -1 and dy == 0:
            movements.append("left")
        elif dx == 0 and dy == 1:
            movements.append("down")
        elif dx == 0 and dy == -1:
            movements.append("up")

        # Otherwise, Nodes are connected. Need to determine connection type.
        elif next_node in current_node.connections:
            connection_type = current_node.connections_types[
                current_node.connections.index(next_node)
            ]

            movements.append(MinimapConnection.convert_to_string(connection_type))
        else:
            breakpoint()
            raise NotImplementedError("Not supposed to reach this point.")

    squeezed_movements = [(k, len(list(g))) for k, g in itertools.groupby(movements)]

    # Lastly, there is a case that cannot be easily addressed through grid-making:
    # Whenever character is using a rope as a "shortcut" for a horizontal walking movement.
    # This case can be identified whenever there is a "JUMP_LEFT_AND_UP" immediately followed by "down" (or right).
    # In this case, we remove both.
    # TODO - See if this can be addressed in grid-making instead (issue now is that weights are difficult to compute)
    for i in range(len(squeezed_movements) - 1):
        if (
            squeezed_movements[i][0] == "JUMP_LEFT_AND_UP"
            and squeezed_movements[i + 1][0] == "down"
        ) or (
            squeezed_movements[i][0] == "JUMP_RIGHT_AND_UP"
            and squeezed_movements[i + 1][0] == "down"
        ):
            if len(squeezed_movements) > 2:
                squeezed_movements.pop(i)
                squeezed_movements.pop(i)
            break

    return squeezed_movements


def _convert_movements_to_actions(
    moves: list[tuple[str, int]], speed: float
) -> list[partial]:
    """
    Converts a series of movements into a series of actions.
    :param moves:
    :param speed:
    :return:
    """
    # We now have a list of movements to perform. When movement is 'left' or 'right', the second
    # element of the tuple is the number of nodes to walk through.
    # This needs to be translated into a duration for the movement.
    actions = []
    for movement in moves:
        if movement[0] in ["left", "right", "up", "down", "FALL_LEFT", "FALL_RIGHT"]:
            secondary_direction = None
            direction = movement[0].split("_")[-1].lower()
            duration = movement[1] / speed
            if movement[0] in ["FALL_LEFT", "FALL_RIGHT"]:
                duration += (
                    3 / speed
                )  # Add extra nodes to make sure character goes beyond platform
            elif direction in ["up", "down"]:
                # In this case, check if this is the last movement, which means the target is on the same platform.
                # If not, add extra nodes to make sure character goes beyond the ladder.
                if not movement == moves[-1]:
                    duration += 5 / speed
            elif movement[0] in ["left", "right"]:
                # In this case, check if the next movement is a simple "up" or "down" movement.
                # If so, we add it as secondary direction, but only once we are close enough to the ladder.
                # Otherwise, we instead remove some nodes such that the character stops before the ladder.
                try:
                    next_move = moves[moves.index(movement) + 1]
                    if next_move[0] in ["up", "down"]:
                        if movement[1] < 5:
                            secondary_direction = next_move[0]
                            duration += 3 / speed  # Make sure we reach the ladder
                        else:
                            # Otherwise, make sure we stop before the ladder and re-calculate on next iteration
                            duration -= 3 / speed
                except IndexError:
                    pass

            act = partial(
                controller.move,
                direction=direction,
                duration=duration,
                secondary_direction=secondary_direction,
            )

        elif movement[0] in ["JUMP_LEFT", "JUMP_RIGHT", "JUMP_DOWN", "JUMP_UP"]:
            direction = movement[0].split("_")[-1].lower()
            act = [
                partial(
                    controller.move,
                    direction=direction,
                    duration=0.05,
                    jump=True,
                    enforce_delay=False,
                    cooldown=0.5,  # Leaves extra time to actually land before next action
                )
            ] * movement[1]

        elif movement[0] == "FALL_ANY":
            raise NotImplementedError("Not supposed to reach this point.")

        elif movement[0] in ["JUMP_LEFT_AND_UP", "JUMP_RIGHT_AND_UP"]:
            direction = movement[0].split("_")[1].lower()
            act = [partial(jump_on_rope, direction=direction)] * movement[1]

        elif movement[0] == "JUMP_ANY_AND_UP":
            raise NotImplementedError("Not supposed to reach this point.")

        elif movement[0] == "PORTAL":
            # Primary direction should be defined through InGameData, outside scope of this function.
            act = [
                partial(
                    controller.move,
                    secondary_direction="up",
                    duration=0.03,
                    enforce_delay=False,
                )
            ] * movement[1]

        elif movement[0] in [
            "TELEPORT_LEFT",
            "TELEPORT_RIGHT",
            "FLASH_JUMP_LEFT",
            "FLASH_JUMP_RIGHT",
        ]:
            raise NotImplementedError("To-do if ever needed.")

        else:
            breakpoint()
            raise NotImplementedError("Not supposed to reach this point.")

        if isinstance(act, list):
            actions.extend(act)
        else:
            actions.append(act)

    return actions
