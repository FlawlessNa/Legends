import logging
from enum import IntEnum
from functools import lru_cache
from itertools import groupby
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder
from typing import NamedTuple

from botting import PARENT_LOG
from botting.controller import KeyboardInputWrapper
from royals.actions import movements_v2
from .map_creation.minimap_grid import ConnectionTypes, MinimapNode, MinimapGrid
from .maple_map import MapleMinimap

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO
DEBUG = True


class MovementTypes(IntEnum):
    """
    Enum to hold the different types of movements.
    """

    WALK_LEFT = 1
    WALK_RIGHT = 2
    CLIMB_UP = 3
    CLIMB_DOWN = 4
    JUMP = 5
    JUMP_LEFT = 6
    JUMP_RIGHT = 7
    JUMP_DOWN = 8
    ENTER_PORTAL = 9
    TELEPORT_LEFT = 10
    TELEPORT_RIGHT = 11
    TELEPORT_UP = 12
    TELEPORT_DOWN = 13
    FLASH_JUMP_LEFT = 14
    FLASH_JUMP_RIGHT = 15
    CROUCH = 16
    END_OF_MOVEMENT = 99  # Last movement, used to release any remaining held key.


class _MovementComponent(NamedTuple):
    """
    NamedTuple to hold the movement type and the duration of the movement.
    """

    movement_type: MovementTypes
    length: int


class MovementHandler:
    _MAX_WALK_SIZE = 5
    _FALL_LEN_EXT = 3

    def __init__(self, handle: int, minimap: MapleMinimap) -> None:
        self.handle = handle
        self.minimap = minimap

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int], grid: MinimapGrid
    ) -> tuple[MinimapNode, ...]:
        path = self._compute_path(start, end, grid)
        self._run_debug(start, end, path)
        return tuple(path)

    @lru_cache
    def _compute_path(
        self, start: tuple[int, int], end: tuple[int, int], grid: MinimapGrid
    ) -> list[MinimapNode]:
        start_node = grid.node(*start)
        end_node = grid.node(*end)
        logger.log(LOG_LEVEL, f"Computing path from {start} to {end}")
        finder = DijkstraFinder() if grid.has_portals else AStarFinder()
        path, _ = finder.find_path(start_node, end_node, grid)
        grid.cleanup()
        return path

    @lru_cache
    def path_into_movements(
        self, path: tuple[MinimapNode, ...], grid: MinimapGrid
    ) -> tuple[_MovementComponent, ...]:

        movements = []
        for current_node, next_node in zip(path, path[1:]):
            current_feature = self.minimap.get_node_info(current_node)
            next_feature = self.minimap.get_node_info(next_node)
            if not current_feature.walkable:
                continue
            elif not next_feature.walkable:
                raise NotImplementedError

            if next_node in grid.neighbors(current_node, include_connections=False):

                dx = next_node.x - current_node.x
                dy = next_node.y - current_node.y
                match (dx, dy, next_feature.is_platform, current_feature.is_platform):
                    case (1, _, True, _):
                        movements.append(
                            _MovementComponent(MovementTypes.WALK_RIGHT, 1)
                        )
                    case (-1, _, True, _):
                        movements.append(_MovementComponent(MovementTypes.WALK_LEFT, 1))
                    case (0, -1, False, _) | (0, -1, True, False):
                        movements.append(_MovementComponent(MovementTypes.CLIMB_UP, 1))
                    case (0, 1, False, _):
                        movements.append(
                            _MovementComponent(MovementTypes.CLIMB_DOWN, 1)
                        )
                    case (0, -1, True, True) | (0, 1, True, True):
                        continue
                    case _:
                        breakpoint()
                        raise NotImplementedError

            elif next_node in current_node.connections:
                connection_type = current_node.get_connection_type(next_node)
                if connection_type is ConnectionTypes.FALL_RIGHT:
                    movements.append(
                        _MovementComponent(MovementTypes.WALK_RIGHT, self._FALL_LEN_EXT)
                    )
                elif connection_type is ConnectionTypes.FALL_LEFT:
                    movements.append(
                        _MovementComponent(MovementTypes.WALK_LEFT, self._FALL_LEN_EXT)
                    )
                elif connection_type is ConnectionTypes.IN_MAP_PORTAL:
                    movements.append(_MovementComponent(MovementTypes.ENTER_PORTAL, 1))
                else:
                    movements.append(
                        _MovementComponent(MovementTypes[connection_type.name], 1)
                    )
            else:
                breakpoint()
                raise NotImplementedError

        logger.log(LOG_LEVEL, f"Movements: {movements}")
        squeezed = []
        for k, group in groupby(movements, key=lambda x: x.movement_type):
            group_list = list(group)
            for i in range(0, len(group_list), self._MAX_WALK_SIZE):
                squeezed.append(
                    _MovementComponent(k, min(len(group_list) - i, self._MAX_WALK_SIZE))
                )
        squeezed.append(_MovementComponent(MovementTypes.END_OF_MOVEMENT, 1))
        return tuple(squeezed)

    @lru_cache
    def movements_into_action(
        self,
        movements: tuple[_MovementComponent, ...],
        grid: MinimapGrid,
        total_duration: float = None,
    ) -> KeyboardInputWrapper:

        structure = None
        for move, upcoming_move in zip(movements, movements[1:]):

            move_type, move_length = move
            duration = move_length / grid.speed
            match move_type:

                case MovementTypes.WALK_LEFT | MovementTypes.WALK_RIGHT:
                    direction = move_type.name.split("_")[-1].lower()
                    secondary = None
                    if upcoming_move.movement_type in (
                        MovementTypes.ENTER_PORTAL,
                        MovementTypes.CLIMB_UP,
                    ):
                        secondary = "up"
                        release_keys = "down"
                        # TODO - See if duration needs to be extended
                    elif upcoming_move.movement_type is MovementTypes.CLIMB_DOWN:
                        # TODO - See if duration needs to be extended
                        secondary = "down"
                        release_keys = "up"
                    else:
                        release_keys = ["up", "down"]
                    structure = movements_v2.move(
                        self.handle,
                        direction,
                        secondary,
                        duration=duration,
                        structure=structure,
                        release_keys=release_keys
                    )

                case MovementTypes.CLIMB_UP | MovementTypes.CLIMB_DOWN:
                    direction = move_type.name.split("_")[-1].lower()
                    secondary = None
                    if upcoming_move.movement_type is MovementTypes.WALK_LEFT:
                        secondary = "left"
                    elif upcoming_move.movement_type is MovementTypes.WALK_RIGHT:
                        secondary = "right"
                    # TODO - See if duration needs to be extended
                    structure = movements_v2.move(
                        self.handle,
                        direction,
                        secondary,
                        duration=duration,
                        structure=structure,
                    )

                case (
                    MovementTypes.JUMP
                    | MovementTypes.JUMP_LEFT
                    | MovementTypes.JUMP_RIGHT
                    | MovementTypes.JUMP_DOWN
                ):
                    direction = (
                        None if move_type is MovementTypes.JUMP
                        else move_type.name.split("_")[-1].lower()
                    )
                    kwargs = dict(
                        handle=self.handle,
                        direction=direction,
                        jump_key=...,
                        structure=structure
                    )
                    for _ in range(move_length - 1):
                        structure = movements_v2.single_jump(**kwargs)
                        kwargs.update(structure=structure)

                    # For the last jump, look at the next move
                    if upcoming_move.movement_type is MovementTypes.CLIMB_UP:
                        # TODO - forced key releases, longer delays.
                        # Todo so, implement a forced release mode on KeyboardInputWrapper
                        structure = movements_v2.jump_on_rope(**kwargs)
                    else:
                        structure = movements_v2.single_jump(**kwargs)

                case MovementTypes.ENTER_PORTAL:
                    structure = movements_v2.move(
                        self.handle, "up", duration=duration, structure=structure
                    )
                case MovementTypes.TELEPORT_LEFT:
                    pass
                case MovementTypes.TELEPORT_RIGHT:
                    pass
                case MovementTypes.TELEPORT_UP:
                    pass
                case MovementTypes.TELEPORT_DOWN:
                    pass
                case (
                    MovementTypes.FLASH_JUMP_LEFT
                    | MovementTypes.FLASH_JUMP_RIGHT
                    | MovementTypes.CROUCH
                ):
                    raise NotImplementedError
                case MovementTypes.END_OF_MOVEMENT if structure is not None:
                    breakpoint()
                    keys = list(
                        key for key in structure.keys_held
                        if key not in structure.forced_key_releases
                    )
                    event = ["keyup"] * len(keys)
                    if keys and event:
                        structure.append(keys, event, 0)  # noqa
                case _:
                    breakpoint()
                    raise NotImplementedError

            # Else just consider current move and disregard previous.
            if structure.duration >= (total_duration or float('inf')):
                structure = structure.truncate(total_duration)
                break

        return structure

    def _run_debug(self, start, end, path) -> None:
        if DEBUG:
            pass
