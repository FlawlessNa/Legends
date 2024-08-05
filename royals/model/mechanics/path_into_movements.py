import time

import cv2
import itertools
import logging

import numpy as np
from functools import partial
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG
from royals.actions import (
    move,
    jump_on_rope,
    teleport,
    single_jump,
)
from royals.model.mechanics import (
    MinimapPathingMechanics,
    MinimapNode,
    MinimapConnection,
)
from .royals_skill import RoyalsSkill

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

DEBUG = True


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
    handle: int,
    jump_key: str,
    teleport_skill: RoyalsSkill = None,
    ign: str = None,
) -> list[partial]:
    """
    Computes the path from current to target using map features.
    Translates this path into movements,  and finally converts those movements
    into in-game actions.
    Returns a nested list where each inner list is a set of inputs to represent a given
    movement.
    :param current: Current minimap position.
    :param target: Target minimap position.
    :param in_game_minimap: The current minimap in-game.
    :param handle: Handle of the game window.
    :param jump_key: Key to use for jumping for the character on the provided window.
    :param teleport_skill: Skill to use for teleporting.
    :param ign: In-game name of the character.
    :return: List of partial where each partial represents a given movement.
    """
    path = _get_path_to_target(current, target, in_game_minimap)
    movements = _translate_path_into_movements(path, in_game_minimap)
    if movements:
        if (
            movements[0] == ("down", 1)
            and not in_game_minimap.grid.node(*current).walkable
        ):
            movements.pop(0)

        elif movements[0][0] in ["up", "down"]:
            displacement = (
                movements[0][1] if movements[0][0] == "down" else -movements[0][1]
            )
            target = current[0], current[1] + displacement
            feature = in_game_minimap.get_feature_containing(current)
            next_feature = in_game_minimap.get_feature_containing(target)
            if feature is not None and feature.is_platform and next_feature.is_platform:
                movements.pop(0)
    return _convert_movements_to_actions(
        movements, in_game_minimap.minimap_speed, handle, jump_key, teleport_skill, ign
    )


def _get_path_to_target(
    current: tuple[int, int],
    target: tuple[int, int],
    in_game_minimap: MinimapPathingMechanics,
) -> list[MinimapNode]:
    """
    Computes the path from current to target using map features.

    :param current: Character position on minimap.
    :param target: Target position on minimap.
    :param in_game_minimap: Minimap implementation which contains minimap coordinates
     for all existing features.
    :return: A series of MinimapNodes that consist of the path to take to reach target.
    """
    start_time = time.time()
    grid = in_game_minimap.grid
    start = grid.node(int(current[0]), int(current[1]))
    end = grid.node(target[0], target[1])
    finder = AStarFinder() if not grid.portals else DijkstraFinder()

    # Find direct path
    direct_path, runs = finder.find_path(start, end, grid)
    best_path = direct_path
    grid.cleanup()

    if DEBUG:
        _debug(in_game_minimap, start, end, best_path)
    print(f"Time to find path {current} -> {target}: {time.time() - start_time}")
    return best_path


def _translate_path_into_movements(
    path: list[MinimapNode], in_game_minimap: MinimapPathingMechanics
) -> list[tuple[str, int]]:
    """
    Translates a path into a series of movements.
    Each movement is represented by a tuple of two items.
    The first item is a str representing the actual movement.
    The second item is an int unit representing the number of nodes/time to move.
    :param path: List of MinimapNodes representing the path to take.
    :return: List of ("movement to do", "number of nodes/times to go through") tuples.
    """

    # We start by translating the path into a series of "movements"
    # (up, down, left, right, jump, teleport, etc.).
    movements = []
    for i in range(len(path) - 1):
        current_node = path[i]
        next_node = path[i + 1]
        current_feature = in_game_minimap.get_feature_containing(
            (current_node.x, current_node.y)
        )
        if current_feature is None:
            continue  # TODO - See if this causes any issue

        next_feature = in_game_minimap.get_feature_containing(
            (next_node.x, next_node.y)
        )

        dx = next_node.x - current_node.x
        dy = next_node.y - current_node.y

        # Cases when there's only 1 unit of displacement; Simply walk in that direction
        # right/left only allowed if node is a platform
        # up/down only allowed if node is a ladder
        if dx == 1 and dy == 0 and current_feature.is_platform:
            movements.append("right")
        elif dx == -1 and dy == 0 and current_feature.is_platform:
            movements.append("left")
        elif (
            current_feature.is_platform and current_feature is next_feature and dx == 0
        ):
            continue
        elif (
            dx == 0
            and dy == 1
            and (current_feature.is_ladder or next_feature.is_ladder)
        ):
            movements.append("down")
        elif (
            dx == 0
            and dy == -1
            and (current_feature.is_ladder or next_feature.is_ladder)
        ):
            movements.append("up")

        # Otherwise, Nodes are connected. Need to determine connection type.
        elif next_node in current_node.connections:
            connection_type = current_node.connections_types[
                current_node.connections.index(next_node)
            ]

            # if more than 1 connection type, prioritize Teleport, if existing.
            if (
                current_node.connections.count(next_node) > 1
                and in_game_minimap.grid.allow_teleport
            ):
                idx = [
                    idx
                    for idx, node in enumerate(current_node.connections)
                    if node == next_node
                ]
                all_connection_types = [current_node.connections_types[i] for i in idx]
                for conn in all_connection_types:
                    if MinimapConnection.convert_to_string(conn).startswith("TELEPORT"):
                        connection_type = conn
                        break

            movements.append(MinimapConnection.convert_to_string(connection_type))
        else:
            raise NotImplementedError("Not supposed to reach this point.")

    squeezed_movements = [(k, len(list(g))) for k, g in itertools.groupby(movements)]
    return squeezed_movements


def _convert_movements_to_actions(
    moves: list[tuple[str, int]],
    speed: float,
    handle: int,
    jump_key: str,
    teleport_skill: RoyalsSkill = None,
    ign: str = None,
) -> list[partial]:
    """
    Converts a series of movements into a series of actions.
    :param moves:
    :param speed:
    :param handle:
    :param jump_key:
    :param teleport_skill:
    :param ign:
    :return:
    """
    actions = []
    for movement in moves:
        if movement[0] in ["left", "right", "up", "down", "FALL_LEFT", "FALL_RIGHT"]:
            # In this case, second element of tuple is number of nodes.
            duration = movement[1] / speed  # Translate nodes into a duration
            direction = movement[0].split("_")[-1].lower()
            secondary_direction = None

            if movement[0] in ["FALL_LEFT", "FALL_RIGHT"]:
                duration += (
                    3 / speed
                )  # Add extra nodes to make sure character goes beyond platform

            elif direction in ["up", "down"]:
                # Check if last movement, meaning target is on the same platform.
                # If not, add extra nodes to make sure character goes beyond the ladder.
                if not movement == moves[-1]:
                    duration += 3 / speed

            elif movement[0] in ["left", "right"]:
                # Check if the next movement is a simple "up" or "down". If so, add it
                # as secondary direction, but only if close enough to the ladder.
                try:
                    next_move = moves[moves.index(movement) + 1]
                    if next_move[0] in ["up", "down", "PORTAL"]:
                        if movement[1] < 5:
                            # Make sure we reach the ladder/portal
                            secondary_direction = (
                                "up" if next_move[0] in ["up", "PORTAL"] else "down"
                            )
                            duration += 3 / speed
                        else:
                            # Otherwise, make sure we stop before the ladder/portal
                            # Will be re-calculated at next iteration
                            duration -= 3 / speed
                except IndexError:
                    # If this is last movement and there's only 1 node, cap duration
                    if movement[1] == 1:
                        duration = 0.05

            actions.append(
                partial(
                    move,
                    handle,
                    direction,
                    secondary_direction=secondary_direction,
                    duration=duration,
                )
            )

        elif movement[0] in ["JUMP_LEFT", "JUMP_RIGHT", "JUMP_DOWN", "JUMP_UP"]:
            direction = movement[0].split("_")[-1].lower()
            num_jumps = movement[1]

            if num_jumps == 1:
                actions.append(partial(single_jump, handle, direction, jump_key))
            elif num_jumps > 1:
                actions.extend(
                    [
                        partial(
                            single_jump,
                            handle,
                            direction,
                            jump_key,
                        )
                    ]
                    * num_jumps
                )

        elif movement[0] == "FALL_ANY":
            raise NotImplementedError("Not supposed to reach this point.")

        elif movement[0] in ["JUMP_LEFT_AND_UP", "JUMP_RIGHT_AND_UP"]:
            direction = movement[0].split("_")[1].lower()
            if movement[1] > 1:
                breakpoint()
                raise NotImplementedError("Not supposed to reach this point.")
            actions.append(partial(jump_on_rope, handle, direction, jump_key))

        elif movement[0] == "JUMP_ANY_AND_UP":
            raise NotImplementedError("Not supposed to reach this point.")

        elif movement[0] == "PORTAL":
            actions.append(partial(move, handle, "up", duration=0.1))

        elif movement[0] in [
            "TELEPORT_LEFT",
            "TELEPORT_RIGHT",
            "TELEPORT_UP",
            "TELEPORT_DOWN",
        ]:
            assert teleport_skill is not None
            direction = movement[0].split("_")[-1].lower()
            actions.append(
                partial(
                    teleport,
                    handle,
                    ign,
                    direction,
                    teleport_skill,
                    num_times=movement[1],
                )
            )

        elif movement[0] in [
            "FLASH_JUMP_LEFT",
            "FLASH_JUMP_RIGHT",
        ]:
            raise NotImplementedError("To-do if ever needed.")

        else:
            breakpoint()
            raise NotImplementedError("Not supposed to reach this point.")

    return actions
