import cv2
import itertools
import logging
import numpy as np
from functools import lru_cache
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG, controller
from royals.actions import movements_v2
from .minimap_mechanics import MinimapConnection, MinimapPathingMechanics, MinimapNode
from .royals_skill import RoyalsSkill

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET
DEBUG = True


class Movements:
    _debug = DEBUG

    def __init__(
        self,
        ign: str,
        handle: int,
        teleport: RoyalsSkill | None,
        minimap: MinimapPathingMechanics,
    ):
        self.ign = ign
        self.handle = handle
        self.teleport = teleport
        self.minimap = minimap
        self.finder = AStarFinder() if not minimap.grid.portals else DijkstraFinder()

    def __hash__(self):
        """Hash the minimap class."""
        return hash((self.ign, self.handle, self.minimap.__class__))

    def __eq__(self, other):
        """Check if the minimap is the same class."""
        return (
            isinstance(other, Movements)
            and self.ign == other.ign
            and self.handle == other.handle
            and self.minimap.__class__ == other.minimap.__class__
        )

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> tuple[MinimapNode, ...]:
        path = self._compute_path(start, end)
        self._run_debug(start, end, path)
        return tuple(path)

    @lru_cache
    def path_into_movements(
        self, path: tuple[MinimapNode, ...]
    ) -> tuple[tuple[str, int], ...]:
        """
        Translates a path into a series of movements.
        Each movement is represented by a tuple of two items.
        The first item is a string representation of the movement to do.
        The second item is an integer unit representing the number of nodes/time to move
        :param path: List of MinimapNodes representing the path to take.
        :return: List of ("movement to do", "number of nodes/times to go through")
        """

        # We start by translating the path into a series of "movements"
        # (up, down, left, right, jump, teleport, etc.).
        movements = []
        for i in range(len(path) - 1):
            current_node = path[i]
            next_node = path[i + 1]
            current_feature = self.minimap.get_feature_containing(
                (current_node.x, current_node.y)
            )
            if current_feature is None:
                continue  # TODO - See if this causes any issue

            next_feature = self.minimap.get_feature_containing(
                (next_node.x, next_node.y)
            )

            dx = next_node.x - current_node.x
            dy = next_node.y - current_node.y

            # Cases when there's only 1 unit of displacement; walk in that direction
            # right/left only allowed if node is a platform
            # up/down only allowed if node is a ladder
            if dx == 1 and dy == 0 and current_feature.is_platform:
                movements.append("right")
            elif dx == -1 and dy == 0 and current_feature.is_platform:
                movements.append("left")
            elif (
                current_feature.is_platform
                and current_feature is next_feature
                and dx == 0
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
            elif (
                current_feature.is_platform
                and next_feature.is_platform
                and dx == 0
                and dy == 1
            ):
                continue

            # Otherwise, Nodes are connected. Need to determine connection type.
            elif next_node in current_node.connections:
                connection_type = current_node.connections_types[
                    current_node.connections.index(next_node)
                ]

                # if more than 1 connection type, prioritize Teleport, if existing.
                if (
                    current_node.connections.count(next_node) > 1
                    and self.minimap.grid.allow_teleport
                ):
                    idx = [
                        idx
                        for idx, node in enumerate(current_node.connections)
                        if node == next_node
                    ]
                    all_connection_types = [
                        current_node.connections_types[i] for i in idx
                    ]
                    for conn in all_connection_types:
                        if MinimapConnection.convert_to_string(conn).startswith(
                            "TELEPORT"
                        ):
                            connection_type = conn
                            break

                movements.append(MinimapConnection.convert_to_string(connection_type))
            else:
                breakpoint()
                raise NotImplementedError("Not supposed to reach this point.")

        squeezed_movements = tuple(
            (k, len(list(g))) for k, g in itertools.groupby(movements)
        )
        return self._fix_movements_for_portals(squeezed_movements)

    @staticmethod
    def _fix_movements_for_portals(
        movements: tuple[tuple[str, int], ...]
    ) -> tuple[tuple[str, int], ...]:
        """
        Whenever a PORTAL movement is present, the previous movement is modified to
        maximizes chances of character properly entering portal.
        :param movements: List of movements to check for a PORTAL type movement.
        :return: List of movements
        """
        indexes = [i for i, m in enumerate(movements) if m[0] == "PORTAL"]
        copied_movements = list(movements)
        adjustment = 0
        for idx in indexes:
            if idx == 0:
                continue
            adj_idx = idx + adjustment
            prev_move, nodes = copied_movements[adj_idx - 1]
            replacement = f"{prev_move}_AND_PORTAL"
            # When previous move is a straight direction, check number of nodes to
            # move. When this is too long, split the movement into 2 movements.
            if prev_move in ["left", "right"] and nodes > 5:
                copied_movements[adj_idx - 1] = (prev_move, 5)
                copied_movements[adj_idx] = (replacement, nodes - 5)
            elif prev_move in ["up", "down"]:
                breakpoint()
            elif prev_move in ["JUMP_RIGHT_AND_UP", "JUMP_LEFT_AND_UP"]:
                breakpoint()
            elif prev_move == "PORTAL":
                breakpoint()
            else:
                adjustment -= 1
                copied_movements[adj_idx] = (replacement, nodes)
                copied_movements.remove((movements[idx - 1]))
        return tuple(copied_movements)

    @lru_cache
    def movements_into_action(
        self,
        movements: tuple[tuple[str, int], ...],
        total_duration: float = None,
        speed_multiplier: float = 1.0,
    ) -> controller.KeyboardInputWrapper:
        """
        # TODO - When refactoring this (and for each transition movement pairs), try using structural pattern matching
        Translates a series of movements into a series of inputs and delays.
        :param movements: series of
            ("movement to do", "number of nodes/times to go through")
        :param total_duration: The maximum duration of the movements.
        :param speed_multiplier: The speed multiplier to apply to the movements.
        :return: KeyboardInputWrapper containing necessary inputs to execute movement.
        """
        speed = self.minimap.get_minimap_speed(speed_multiplier)
        structure = None
        direction = None
        for idx, move in enumerate(movements):
            if move[0].removesuffix("_AND_PORTAL") in [
                "left",
                "right",
                "up",
                "down",
                "FALL_LEFT",
                "FALL_RIGHT",
            ]:
                duration = move[1] / speed
                direction = move[0].removesuffix("_AND_PORTAL").split("_")[-1].lower()
                secondary_direction = "up" if move[0].endswith("_AND_PORTAL") else None

                if move[0].startswith("FALL"):
                    # Add extra nodes to ensure character goes beyond the edge
                    duration += 3 / speed
                elif direction in ["up", "down"]:
                    # Check if last movement, meaning target is on the same platform.
                    # If not, add extra nodes to make sure character goes beyond ladder.
                    if not move == movements[-1]:
                        duration += 5 / speed
                elif direction in ["left", "right"]:
                    # Check if next movement is a simple "up" or "down". If so, add it
                    # as secondary direction, but only if close enough to the ladder.
                    try:
                        next_move = movements[idx + 1]
                        if next_move[0] in ["up", "down"]:
                            if move[1] < 5:
                                # Make sure we reach the ladder portal
                                secondary_direction = next_move[0]
                                duration += 5 / speed
                            else:
                                # Otherwise, make sure we stop before ladder/portal
                                duration -= 5 / speed
                    except IndexError:
                        # If this is last movement and there's only 1 node, cap duration
                        if move[1] == 1:
                            duration = 0.05
                structure = movements_v2.move(
                    self.handle,
                    direction,  # noqa
                    secondary_direction,
                    duration=duration,
                    structure=structure,
                )
            elif move[0] in ["JUMP_LEFT", "JUMP_RIGHT", "JUMP_DOWN", "JUMP_UP"]:
                direction = move[0].split("_")[-1].lower()
                num_jumps = move[1]
                for _ in range(num_jumps):
                    structure = movements_v2.single_jump(
                        self.handle,
                        direction,  # noqa
                        controller.key_binds(self.ign)["jump"],
                        structure=structure,
                    )
            elif move[0] in ["JUMP_LEFT_AND_UP", "JUMP_RIGHT_AND_UP"]:
                direction = move[0].split("_")[1].lower()
                if move[1] > 1:
                    breakpoint()
                    raise NotImplementedError("Not supposed to reach this point.")
                # Attempting to force all key releases when jump on rope is part of structure
                if structure is not None:
                    for key in structure.keys_held:
                        structure.append(
                            key,
                            "keyup",
                            next(controller.random_delay)
                        )
                structure = movements_v2.jump_on_rope(
                    self.handle,
                    direction,  # noqa
                    controller.key_binds(self.ign)["jump"],
                    structure=structure,
                )
            elif move[0] == "PORTAL":
                primary = direction or "up"
                secondary = "up" if primary != "up" else None
                structure = movements_v2.move(
                    self.handle, primary, secondary, duration=0.1, structure=structure
                )
            elif move[0] in [
                "TELEPORT_LEFT",
                "TELEPORT_RIGHT",
                "TELEPORT_UP",
                "TELEPORT_DOWN",
            ]:
                direction = move[0].split("_")[-1].lower()
                structure = movements_v2.teleport(
                    self.handle,
                    self.ign,
                    direction,  # noqa
                    self.teleport,
                    num_times=move[1],
                    structure=structure,
                )
            elif move[0] in [
                "TELEPORT_LEFT_AND_PORTAL",
                "TELEPORT_RIGHT_AND_PORTAL",
                "TELEPORT_UP_AND_PORTAL",
                "TELEPORT_DOWN_AND_PORTAL",
            ]:
                direction = move[0].removesuffix("_AND_PORTAL").split("_")[-1].lower()
                structure = movements_v2.teleport(
                    self.handle,
                    self.ign,
                    direction,  # noqa
                    self.teleport,
                    num_times=move[1],
                    structure=structure,
                    repeat_key="up",
                )
            elif move[0] in ["JUMP_RIGHT_AND_PORTAL", "JUMP_LEFT_AND_PORTAL"]:
                direction = move[0].split("_")[1].lower()
                structure = movements_v2.single_jump(
                    self.handle,
                    direction,  # noqa
                    controller.key_binds(self.ign)["jump"],
                    structure=structure,
                    repeat_key="up",
                )
            else:
                breakpoint()
                raise NotImplementedError("Not supposed to reach this point.")

            if idx == len(movements) - 1:
                # If we get all the way to the last movement within the path, then
                # We release directional keys but not enforced.
                to_release = list(structure.keys_held)
                structure.append(
                    to_release,
                    ['keyup'] * len(to_release),  # noqa
                    next(controller.random_delay)
                )
            if (
                total_duration is not None
                and structure is not None
                and structure.duration >= total_duration
            ):
                break
            elif "PORTAL" in move[0]:
                break

        if structure is not None and total_duration is not None:
            return structure.truncate(total_duration)
        elif structure is not None:
            return structure

    @lru_cache
    def _compute_path(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> list[MinimapNode]:
        start_node = self.minimap.grid.node(*start)
        end_node = self.minimap.grid.node(*end)
        path, _ = self.finder.find_path(start_node, end_node, self.minimap.grid)
        self.minimap.grid.cleanup()
        return path

    def _run_debug(
        self, start: tuple[int, int], end: tuple[int, int], path: list[MinimapNode]
    ) -> None:
        if not self._debug:
            return
        canvas = np.zeros(
            (self.minimap.map_area_height, self.minimap.map_area_width),
            dtype=np.uint8,
        )
        canvas = self.minimap._preprocess_img(canvas)
        path_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
        cv2.drawMarker(
            path_img, (start[0], start[1]), (0, 0, 255), cv2.MARKER_CROSS, markerSize=3
        )
        cv2.drawMarker(
            path_img, (end[0], end[1]), (255, 0, 0), cv2.MARKER_CROSS, markerSize=3
        )
        for node in path:
            path_img[node.y, node.x] = (0, 255, 0)
        path_img = cv2.resize(path_img, None, fx=5, fy=5)
        cv2.imshow(f"_DEBUG_ Mode - PathFinding {self.ign}", path_img)
        cv2.waitKey(1)
