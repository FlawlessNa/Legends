import cv2
import logging
import numpy as np
from enum import IntEnum
from functools import lru_cache
from itertools import groupby
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder
from typing import NamedTuple

from botting import PARENT_LOG
from botting.controller import KeyboardInputWrapper, key_binds
from maple.actions import movements_v2
from maple.model.characters.maple_skills import MapleSkill
from .minimap_creation.minimap_grid import ConnectionTypes, MinimapNode, MinimapGrid
from .maple_map import MapleMinimap

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


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


_NARROW_PLATFORM_THRESHOLD = 5  # platforms narrower than this (pixels) get a direction-stop after landing

_PRECISION_PRE_STOP = frozenset({
    MovementTypes.JUMP,
    MovementTypes.JUMP_LEFT,
    MovementTypes.JUMP_RIGHT,
    MovementTypes.JUMP_DOWN,
    MovementTypes.ENTER_PORTAL,
})

_JUMP_CONNECTION_TYPES = frozenset({
    ConnectionTypes.JUMP,
    ConnectionTypes.JUMP_LEFT,
    ConnectionTypes.JUMP_RIGHT,
    ConnectionTypes.JUMP_DOWN,
})


class _MovementComponent(NamedTuple):
    """
    NamedTuple to hold the movement type and the duration of the movement.
    """

    movement_type: MovementTypes
    length: int
    narrow: bool = False  # True when this jump lands on a narrow platform (≤ _NARROW_PLATFORM_THRESHOLD px)


def compile_movements(
    initial_held_keys: frozenset[str] | None,
    *,
    movements: tuple[_MovementComponent, ...],
    handle: int,
    ign: str,
    speed: float,
    teleport: MapleSkill | None = None,
    total_duration: float = None,
    always_release: bool = False,
) -> KeyboardInputWrapper | None:
    """
    Compiles a Movement Plan into an Input Sequence.

    Module-level and keyed only on plain data so it can be pickled into an
    ActionRequest and run at dispatch (see `controller.compile_and_send`) - a
    `MovementHandler` cannot, since its per-instance `lru_cache` wrappers are not
    picklable. `MovementHandler.movements_into_action` delegates here, so the offline
    lab and the live path compile through the exact same code.

    :param initial_held_keys: Movement keys held before compilation starts. Passed
        through to the first builder call (the only one that would otherwise query
        live Win32 state). Live callers feed it the Held-Keys Ledger; the offline lab
        feeds it a fixture. None falls back to the live query, which is only correct
        in Main Process.
    :param movements: The Movement Plan to compile.
    :param speed: The grid's speed, which converts a movement's length to a duration.
    :param total_duration: When given, compilation stops once the sequence reaches it.
    :param always_release: Force-release every key still held at the end of the
        sequence. This is the flag form of what `_always_release_keys_on_actions`
        used to do by post-processing a compiled Action in the Engine process.
    :return: The Input Sequence, or None when the plan compiles to nothing.
    """
    structure = None
    for move, upcoming_move in zip(movements, movements[1:]):

        move_type, move_length = move.movement_type, move.length
        duration = move_length / speed
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
                    handle,
                    direction,  # noqa
                    secondary,
                    duration=duration,
                    structure=structure,
                    release_keys=release_keys,
                    initial_held_keys=initial_held_keys,
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
                    handle,
                    direction,  # noqa
                    secondary,
                    duration=duration,
                    structure=structure,
                    initial_held_keys=initial_held_keys,
                )

            case (
                MovementTypes.JUMP
                | MovementTypes.JUMP_LEFT
                | MovementTypes.JUMP_RIGHT
                | MovementTypes.JUMP_DOWN
            ):
                direction = (
                    'up' if move_type is MovementTypes.JUMP
                    else move_type.name.split("_")[-1].lower()
                )
                kwargs = dict(
                    handle=handle,
                    direction=direction,
                    jump_key=key_binds(ign)['jump'],
                    structure=structure,
                    initial_held_keys=initial_held_keys,
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
                    if move.narrow:
                        # Narrow platform: release horizontal key on landing so the
                        # character doesn't walk off the edge after touching down.
                        held_dir = next(
                            (k for k in structure.keys_held if k in ('left', 'right')),
                            None
                        )
                        if held_dir:
                            structure.append(held_dir, "keyup", 0)

            case MovementTypes.ENTER_PORTAL:
                structure = movements_v2.move(
                    handle,
                    "up",
                    duration=duration,
                    structure=structure,
                    initial_held_keys=initial_held_keys,
                )

            case (
                MovementTypes.TELEPORT_LEFT
                | MovementTypes.TELEPORT_RIGHT
                | MovementTypes.TELEPORT_UP
                | MovementTypes.TELEPORT_DOWN
            ):
                direction = move_type.name.split("_")[-1].lower()
                repeat_key = None
                if upcoming_move.movement_type in (
                        MovementTypes.ENTER_PORTAL,
                        MovementTypes.CLIMB_UP,
                ):
                    repeat_key='up'
                structure = movements_v2.teleport(
                    handle,
                    ign,
                    direction, # noqa
                    teleport,
                    move_length,
                    structure=structure,
                    repeat_key=repeat_key,
                    initial_held_keys=initial_held_keys,
                )
            case (
                MovementTypes.FLASH_JUMP_LEFT
                | MovementTypes.FLASH_JUMP_RIGHT
                | MovementTypes.CROUCH
            ):
                raise NotImplementedError(f"{move_type.name} builder not implemented")
            case _:
                raise NotImplementedError(f"Unhandled movement type {move_type!r}")

        # Else just consider current move and disregard previous.
        if structure.duration >= (total_duration or float('inf')):
            # Before hard-truncating: if the next move is precision-sensitive,
            # release the horizontal key now so the next chunk starts from a
            # stopped position and can execute the jump from the correct spot.
            if upcoming_move.movement_type in _PRECISION_PRE_STOP:
                held_dir = next(
                    (k for k in structure.keys_held if k in ('left', 'right')),
                    None
                )
                if held_dir:
                    structure.append(held_dir, "keyup", 0)
            structure = structure.truncate(total_duration)
            break
    else:
        # Loop ran to completion (no truncation): release any keys still held
        # so the last Step satisfies the Terminal Release invariant. `move`
        # never reaches the END_OF_MOVEMENT sentinel appended by
        # `_path_into_movements_uncached` (zip stops one short of it), so this
        # can't be handled as a movement-type case in the loop body above.
        if structure is not None:
            keys = list(
                key for key in structure.keys_held
                if key not in structure.forced_key_releases
            )
            event = ["keyup"] * len(keys)
            if keys and event:
                structure.append(keys, event, 0)  # noqa

    if always_release and structure is not None:
        for key in structure.keys_held:
            if key not in structure.forced_key_releases:
                structure.forced_key_releases.append(key)
    return structure


class MovementHandler:
    _MAX_WALK_SIZE = 5
    _FALL_LEN_EXT = 3
    _CACHE_MAXSIZE = 256  # bounded: avoids unbounded growth from stale entries on grid edits

    def __init__(
        self,
        handle: int,
        minimap: MapleMinimap,
        ign: str,
        teleport: MapleSkill | None = None,
        *,
        debug: bool = False,
    ) -> None:
        self.handle = handle
        self.minimap = minimap
        self.ign = ign
        self.teleport = teleport
        self._debug = debug
        # Per-instance, bounded caches: an `@lru_cache` on the method itself would key
        # on `self`, pinning every handler ever created in memory for the process
        # lifetime. Binding the cache here scopes it (and its staleness on grid edits)
        # to this instance, so it's freed when the handler is.
        self._compute_path = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._compute_path_uncached
        )
        self.path_into_movements = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._path_into_movements_uncached
        )
        self.movements_into_action = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._movements_into_action_uncached
        )

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int], grid: MinimapGrid
    ) -> tuple[MinimapNode, ...]:
        path = self._compute_path(start, end, grid)
        self._run_debug(start, end, path)
        return tuple(path)

    def _compute_path_uncached(
        self, start: tuple[int, int], end: tuple[int, int], grid: MinimapGrid
    ) -> list[MinimapNode]:
        start_node = grid.node(*start)
        end_node = grid.node(*end)
        logger.log(LOG_LEVEL, f"Computing path from {start} to {end}")
        # finder = DijkstraFinder() if grid.has_portals else AStarFinder()
        finder = DijkstraFinder()
        path, _ = finder.find_path(start_node, end_node, grid)
        grid.cleanup()
        return path

    def _path_into_movements_uncached(
        self, path: tuple[MinimapNode, ...], grid: MinimapGrid
    ) -> tuple[_MovementComponent, ...]:

        movements = []
        for current_node, next_node in zip(path, path[1:]):
            current_feature = self.minimap.get_node_info(current_node)
            next_feature = self.minimap.get_node_info(next_node)
            if not current_node.walkable:
                continue
            elif not next_node.walkable:
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
                    case (0, 1, False, _) | (0, 1, True, False):
                        movements.append(
                            _MovementComponent(MovementTypes.CLIMB_DOWN, 1)
                        )
                    case (0, -1, True, True) | (0, 1, True, True):
                        continue
                    case _:
                        raise NotImplementedError(
                            f"Unhandled adjacency {(dx, dy, next_feature.is_platform, current_feature.is_platform)} "
                            f"between {current_node} and {next_node}"
                        )

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
                    move_type = MovementTypes[connection_type.name]
                    if connection_type in _JUMP_CONNECTION_TYPES:
                        is_narrow = (
                            next_feature.is_platform
                            and next_feature.width <= _NARROW_PLATFORM_THRESHOLD
                        )
                        movements.append(_MovementComponent(move_type, 1, narrow=is_narrow))
                    else:
                        movements.append(_MovementComponent(move_type, 1))
            else:
                raise NotImplementedError(
                    f"No neighbor/connection edge between {current_node} and {next_node}"
                )

        logger.log(LOG_LEVEL, f"Movements: {movements}")
        squeezed = []
        for k, group in groupby(movements, key=lambda x: x.movement_type):
            group_list = list(group)
            is_narrow = group_list[0].narrow  # preserved from first element in group
            for i in range(0, len(group_list), self._MAX_WALK_SIZE):
                squeezed.append(
                    _MovementComponent(k, min(len(group_list) - i, self._MAX_WALK_SIZE), is_narrow)
                )
        squeezed.append(_MovementComponent(MovementTypes.END_OF_MOVEMENT, 1))
        return tuple(squeezed)

    def _movements_into_action_uncached(
        self,
        movements: tuple[_MovementComponent, ...],
        grid: MinimapGrid,
        total_duration: float = None,
        initial_held_keys: frozenset[str] | None = None,
    ) -> KeyboardInputWrapper | None:
        """
        Offline/tooling entry point. The live path compiles at dispatch through
        `compile_movements` directly - see `controller.compile_and_send`.
        :param initial_held_keys: Movement keys held before compilation starts.
        """
        return compile_movements(
            initial_held_keys,
            movements=movements,
            handle=self.handle,
            ign=self.ign,
            speed=grid.speed,
            teleport=self.teleport,
            total_duration=total_duration,
        )

    def _run_debug(
        self, start: tuple[int, int], end: tuple[int, int], path: list[MinimapNode]
    ) -> None:
        if not self._debug:
            return
        minimap_img = (self.minimap.modified_minimap > 0).view(np.uint8) * 255
        minimap_img = cv2.cvtColor(minimap_img, cv2.COLOR_GRAY2BGR)
        cv2.drawMarker(
            minimap_img,
            (start[0], start[1]),
            (0, 0, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=3
        )
        cv2.drawMarker(
            minimap_img,
            (end[0], end[1]),
            (255, 0, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=3
        )
        for node in path:
            minimap_img[node.y, node.x] = (0, 255, 0)
        minimap_img = cv2.resize(minimap_img, None, fx=5, fy=5)
        cv2.imshow(
            f"_DEBUG_ Mode - Pathfinding {self.ign}2",
            minimap_img,
        )
        cv2.waitKey(1)
