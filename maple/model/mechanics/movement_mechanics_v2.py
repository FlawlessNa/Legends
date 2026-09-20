import logging
from enum import IntEnum
from functools import lru_cache
from itertools import groupby, pairwise
from typing import Literal, NamedTuple

import cv2
import numpy as np
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG
from botting.controller import (
    EVENTS,
    NO_COMPONENT,
    InputState,
    KeyboardInputWrapper,
    key_binds,
)
from maple.actions import movements_v2
from maple.model.characters.maple_skills import MapleSkill

from .maple_map import MapleMinimap
from .minimap_creation.minimap_grid import ConnectionTypes, MinimapGrid, MinimapNode

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

Direction = Literal["left", "right", "up", "down"]

# A `MovementTypes` member's name carries its direction as a suffix, but
# `.name.split("_")[-1].lower()` is a plain `str` to the type checker where every
# builder takes a `Direction`. Going through this table narrows it without a cast, and
# raises on a movement type whose suffix is not a direction.
_DIRECTIONS: dict[str, Direction] = {
    "left": "left",
    "right": "right",
    "up": "up",
    "down": "down",
}


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


# Platforms this narrow (minimap pixels) get a direction-stop after landing. The
# default only: `MovementHandler` carries its own, so a Trial batch can sweep it as a
# Knob without touching production's value.
_NARROW_PLATFORM_THRESHOLD = 5

# A start node this close (minimap pixels) to its platform's end, in the travel
# direction, gets the edge-departure flag (PM3). Same shape as the threshold above:
# module default only, `MovementHandler` carries its own per-instance value.
_EDGE_DEPARTURE_THRESHOLD = 5

_PRECISION_PRE_STOP = frozenset(
    {
        MovementTypes.JUMP,
        MovementTypes.JUMP_LEFT,
        MovementTypes.JUMP_RIGHT,
        MovementTypes.JUMP_DOWN,
        MovementTypes.ENTER_PORTAL,
    }
)

_JUMP_CONNECTION_TYPES = frozenset(
    {
        ConnectionTypes.JUMP,
        ConnectionTypes.JUMP_LEFT,
        ConnectionTypes.JUMP_RIGHT,
        ConnectionTypes.JUMP_DOWN,
    }
)

_TELEPORT_CONNECTION_TYPES = frozenset(
    {
        ConnectionTypes.TELEPORT_LEFT,
        ConnectionTypes.TELEPORT_RIGHT,
        ConnectionTypes.TELEPORT_UP,
        ConnectionTypes.TELEPORT_DOWN,
    }
)

# Landing width (PM2) applies to any jump or teleport that lands on a platform.
_NARROW_CONNECTION_TYPES = _JUMP_CONNECTION_TYPES | _TELEPORT_CONNECTION_TYPES

# Edge departure (PM3) only has a "travel direction" sense for horizontal gestures -
# a platform has a left/right end, not an up/down one.
_EDGE_DEPARTURE_CONNECTION_TYPES = frozenset(
    {
        ConnectionTypes.JUMP_LEFT,
        ConnectionTypes.JUMP_RIGHT,
        ConnectionTypes.TELEPORT_LEFT,
        ConnectionTypes.TELEPORT_RIGHT,
    }
)


class _MovementComponent(NamedTuple):
    """
    NamedTuple to hold the movement type and the duration of the movement.
    """

    movement_type: MovementTypes
    length: int
    narrow: bool = False  # True when this jump/teleport lands on a narrow platform (≤ narrow_platform_threshold px)
    edge_departure: bool = False  # True when this jump/teleport starts within edge_departure_threshold px of its platform's end, in the travel direction


def compile_movements(
    initial_state: InputState | None,
    *,
    movements: tuple[_MovementComponent, ...],
    handle: int,
    ign: str,
    speed: float,
    teleport: MapleSkill | None = None,
    total_duration: float | None = None,
    always_release: bool = False,
) -> KeyboardInputWrapper | None:
    """
    Compiles a Movement Plan into an Input Sequence.

    Module-level and keyed only on plain data so it can be pickled into an
    ActionRequest and run at dispatch (see `controller.compile_and_send`) - a
    `MovementHandler` cannot, since its per-instance `lru_cache` wrappers are not
    picklable. `MovementHandler.movements_into_action` delegates here, so the offline
    lab and the live path compile through the exact same code.

    :param initial_state: The keyboard state before compilation starts - the movement
        keys held, which key owns typematic, and how long it has owned. Passed through
        to the first builder call (the only one that would otherwise query live Win32
        state). Live callers feed it the Held-Keys Ledger; the offline lab feeds it a
        fixture. None falls back to the live query, which is only correct in Main
        Process.
    :param movements: The Movement Plan to compile.
    :param speed: The grid's speed, which converts a movement's length to a duration.
    :param total_duration: When given, compilation stops once the sequence reaches it.
    :param always_release: Force-release every key still held at the end of the
        sequence. This is the flag form of what `_always_release_keys_on_actions`
        used to do by post-processing a compiled Action in the Engine process.
    :return: The Input Sequence, or None when the plan compiles to nothing.
    """
    structure = None
    for origin, (move, upcoming_move) in enumerate(pairwise(movements)):
        # Provenance: every Step the builders below emit belongs to component `origin`.
        # The cursor moves here, ahead of the build, because a builder appends and
        # inserts as it goes and the wrapper stamps each Step as it lands - no
        # after-the-fact tail-fill, which an `insert` in the middle of a component
        # would misalign. The first component is the exception: its builder
        # *constructs* the wrapper, so there is no object to set the cursor on until it
        # returns, and its Steps are stamped `NO_COMPONENT` by default. `attribute`
        # below claims them.
        if structure is not None:
            structure.current_origin = origin
        move_type, move_length = move.movement_type, move.length
        duration = move_length / speed
        match move_type:
            case MovementTypes.WALK_LEFT | MovementTypes.WALK_RIGHT:
                direction = _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                secondary: Direction | None = None
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
                    direction,
                    secondary,
                    duration=duration,
                    structure=structure,
                    release_keys=release_keys,
                    initial_state=initial_state,
                )

            case MovementTypes.CLIMB_UP | MovementTypes.CLIMB_DOWN:
                direction = _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                secondary = None
                if upcoming_move.movement_type is MovementTypes.WALK_LEFT:
                    secondary = "left"
                elif upcoming_move.movement_type is MovementTypes.WALK_RIGHT:
                    secondary = "right"
                # TODO - See if duration needs to be extended
                structure = movements_v2.move(
                    handle,
                    direction,
                    secondary,
                    duration=duration,
                    structure=structure,
                    initial_state=initial_state,
                )

            case (
                MovementTypes.JUMP
                | MovementTypes.JUMP_LEFT
                | MovementTypes.JUMP_RIGHT
                | MovementTypes.JUMP_DOWN
            ):
                direction = (
                    "up"
                    if move_type is MovementTypes.JUMP
                    else _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                )
                jump_key = key_binds(ign)["jump"]
                for _ in range(move_length - 1):
                    structure = movements_v2.single_jump(
                        handle,
                        direction,
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                    )

                # For the last jump, look at the next move
                if upcoming_move.movement_type is MovementTypes.CLIMB_UP:
                    # TODO - forced key releases, longer delays.
                    # Todo so, implement a forced release mode on KeyboardInputWrapper
                    structure = movements_v2.jump_on_rope(
                        handle,
                        # `direction` is 'up' for a plain JUMP and 'down' for a
                        # JUMP_DOWN, neither of which `jump_on_rope` accepts: it
                        # presses 'up' itself. For 'up', that's pressed twice and
                        # released once, leaving it held (issue #111 - open; what a
                        # straight-up jump onto a rope should compile to needs a
                        # client to settle). For 'down', `jump_on_rope` no longer
                        # double-releases it (issue #131 - its own 'up' press can
                        # already clear 'down' as the opposite key). Passed through
                        # unchanged rather than guessed at either way. Latent - the
                        # `**kwargs` dict this call used to go through erased the
                        # type.
                        direction,  # pyright: ignore[reportArgumentType]
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                    )
                else:
                    structure = movements_v2.single_jump(
                        handle,
                        direction,
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                    )
                    if move.narrow:
                        # Narrow platform: release horizontal key on landing so the
                        # character doesn't walk off the edge after touching down.
                        held_dir = next(
                            (k for k in structure.keys_held if k in ("left", "right")),
                            None,
                        )
                        if held_dir:
                            structure.append(held_dir, "keyup", 0)

            case MovementTypes.ENTER_PORTAL:
                structure = movements_v2.move(
                    handle,
                    "up",
                    duration=duration,
                    structure=structure,
                    initial_state=initial_state,
                )

            case (
                MovementTypes.TELEPORT_LEFT
                | MovementTypes.TELEPORT_RIGHT
                | MovementTypes.TELEPORT_UP
                | MovementTypes.TELEPORT_DOWN
            ):
                if teleport is None:
                    raise ValueError(
                        f"{move_type.name} is in the Movement Plan, but no teleport "
                        f"skill was supplied to compile it with."
                    )
                direction = _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                repeat_key = None
                if upcoming_move.movement_type in (
                    MovementTypes.ENTER_PORTAL,
                    MovementTypes.CLIMB_UP,
                ):
                    repeat_key = "up"
                structure = movements_v2.teleport(
                    handle,
                    ign,
                    direction,
                    teleport,
                    move_length,
                    structure=structure,
                    repeat_key=repeat_key,
                    initial_state=initial_state,
                )
            case (
                MovementTypes.FLASH_JUMP_LEFT
                | MovementTypes.FLASH_JUMP_RIGHT
                | MovementTypes.CROUCH
            ):
                raise NotImplementedError(f"{move_type.name} builder not implemented")
            case _:
                raise NotImplementedError(f"Unhandled movement type {move_type!r}")

        structure.attribute(origin)

        # Else just consider current move and disregard previous.
        if total_duration is not None and structure.duration >= total_duration:
            structure = structure.truncate(total_duration)
            # The cut lands mid-walk with the horizontal key still down, and the
            # next chunk opens on a jump or a portal - a move that misses unless
            # the character is standing still. Release the direction so the next
            # chunk starts from a stopped position.
            #
            # Appended to the *truncated* copy, not to `structure` ahead of the
            # cut: `truncate` copies Steps `while result.duration < limit`, and
            # this branch is only reached once the duration has already passed
            # the limit, so a release appended before the call is past the budget
            # by construction and is never copied. That is issue #100 - the
            # pre-stop had never emitted a Step on any path.
            #
            # Reading `keys_held` off the copy rather than off the full sequence
            # also keeps the release honest: a direction whose keydown fell past
            # the cut is not down, and releasing it would be a phantom release
            # (**A6**).
            #
            # The zero-delay Step still costs `OVERHEAD`, so the sequence
            # overshoots `total_duration` by ~1ms. `truncate` already overshoots
            # by the delay of the Step that crosses the limit, so this stays
            # inside the existing contract rather than widening it.
            if (
                upcoming_move.movement_type in _PRECISION_PRE_STOP
                or upcoming_move.edge_departure
            ):
                held_dir = next(
                    (k for k in structure.keys_held if k in ("left", "right")), None
                )
                if held_dir:
                    structure.append(held_dir, "keyup", 0)
            break
        elif upcoming_move.edge_departure:
            # An edge departure wants the same stop even when no cut lands here -
            # unlike `_PRECISION_PRE_STOP`, which only ever fires as a side effect
            # of truncation. Safe to append directly to `structure` (not a
            # truncated copy): this branch is only reached when no truncation
            # happened this iteration, so the append issue #100 guards against
            # does not apply here.
            held_dir = next(
                (k for k in structure.keys_held if k in ("left", "right")), None
            )
            if held_dir:
                structure.append(held_dir, "keyup", 0)
    else:
        # Loop ran to completion (no truncation): release any keys still held
        # so the last Step satisfies the Terminal Release invariant. `move`
        # never reaches the END_OF_MOVEMENT sentinel appended by
        # `_path_into_movements_uncached` (zip stops one short of it), so this
        # can't be handled as a movement-type case in the loop body above.
        if structure is not None:
            keys = [
                key
                for key in structure.keys_held
                if key not in structure.forced_key_releases
            ]
            if keys:
                events: list[EVENTS] = ["keyup"] * len(keys)
                # No component produced this release - it closes the sequence, not a
                # gesture - so it carries the sentinel rather than inheriting the last
                # component the cursor named. Same reasoning as the precision pre-stop,
                # whose cursor `truncate` resets for it.
                structure.current_origin = NO_COMPONENT
                structure.append(keys, events, 0)

    if always_release and structure is not None:
        for key in structure.keys_held:
            if key not in structure.forced_key_releases:
                structure.forced_key_releases.append(key)
    return structure


class MovementHandler:
    _MAX_WALK_SIZE = 5
    _FALL_LEN_EXT = 3
    _CACHE_MAXSIZE = (
        256  # bounded: avoids unbounded growth from stale entries on grid edits
    )

    def __init__(
        self,
        handle: int,
        minimap: MapleMinimap,
        ign: str,
        teleport: MapleSkill | None = None,
        *,
        debug: bool = False,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
    ) -> None:
        """
        :param narrow_platform_threshold: Platform width (minimap pixels) at or below
            which a jump or teleport onto it is marked `narrow`, so compilation adds
            the landing direction-stop. `None` is the module default, which is what
            production wants. It is per-instance because it is a **Knob** a Trial
            batch sweeps (`maple.calibration.specs.Knobs`), and it shapes the
            Movement Plan here, in the Engine - `compile_movements` reads the
            component's `narrow` flag and never the threshold, so the send path is
            untouched.
        :param edge_departure_threshold: Distance (minimap pixels) from a platform's
            end, in the travel direction, within which a jump or teleport's start
            node is marked `edge_departure`, so compilation adds the pre-departure
            stop. Same shape as `narrow_platform_threshold`: `None` is the module
            default, per-instance because it is a Knob, and read by
            `compile_movements` only through the component's `edge_departure` flag.
        """
        self.handle = handle
        self.minimap = minimap
        self.ign = ign
        self.teleport = teleport
        self.narrow_platform_threshold = (
            _NARROW_PLATFORM_THRESHOLD
            if narrow_platform_threshold is None
            else narrow_platform_threshold
        )
        self.edge_departure_threshold = (
            _EDGE_DEPARTURE_THRESHOLD
            if edge_departure_threshold is None
            else edge_departure_threshold
        )
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
        # Per-cycle pathing traces, so DEBUG is the honest level. Their Telemetry
        # Record form waits on issue #12, which owns `MovementPayload`.
        logger.debug("Computing path from %s to %s", start, end)
        # finder = DijkstraFinder() if grid.has_portals else AStarFinder()
        finder = DijkstraFinder()
        path, _ = finder.find_path(start_node, end_node, grid)
        grid.cleanup()
        return path

    def _path_into_movements_uncached(
        self, path: tuple[MinimapNode, ...], grid: MinimapGrid
    ) -> tuple[_MovementComponent, ...]:

        movements = []
        for current_node, next_node in pairwise(path):
            current_feature = self.minimap.get_node_info(current_node)
            next_feature = self.minimap.get_node_info(next_node)
            if not current_node.walkable:
                continue
            elif not next_node.walkable:
                raise NotImplementedError

            if next_node in grid.adjacent_nodes(current_node):
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
                    is_narrow = False
                    is_edge_departure = False
                    if connection_type in _NARROW_CONNECTION_TYPES:
                        is_narrow = (
                            next_feature.is_platform
                            and next_feature.width <= self.narrow_platform_threshold
                        )
                    if (
                        connection_type in _EDGE_DEPARTURE_CONNECTION_TYPES
                        and current_feature.is_platform
                    ):
                        edge_direction = connection_type.name.split("_")[-1].lower()
                        if edge_direction == "right":
                            is_edge_departure = (
                                current_feature.right - current_node.x
                                <= self.edge_departure_threshold
                            )
                        elif edge_direction == "left":
                            is_edge_departure = (
                                current_node.x - current_feature.left
                                <= self.edge_departure_threshold
                            )
                    movements.append(
                        _MovementComponent(
                            move_type,
                            1,
                            narrow=is_narrow,
                            edge_departure=is_edge_departure,
                        )
                    )
            else:
                raise NotImplementedError(
                    f"No neighbor/connection edge between {current_node} and {next_node}"
                )

        logger.debug("Movements: %s", movements)
        squeezed = []
        for k, group in groupby(movements, key=lambda x: x.movement_type):
            group_list = list(group)
            # Both flags preserved from the first element in the group.
            is_narrow = group_list[0].narrow
            is_edge_departure = group_list[0].edge_departure
            for i in range(0, len(group_list), self._MAX_WALK_SIZE):
                squeezed.append(
                    _MovementComponent(
                        k,
                        min(len(group_list) - i, self._MAX_WALK_SIZE),
                        is_narrow,
                        is_edge_departure,
                    )
                )
        squeezed.append(_MovementComponent(MovementTypes.END_OF_MOVEMENT, 1))
        return tuple(squeezed)

    def _movements_into_action_uncached(
        self,
        movements: tuple[_MovementComponent, ...],
        grid: MinimapGrid,
        total_duration: float | None = None,
        initial_state: InputState | None = None,
    ) -> KeyboardInputWrapper | None:
        """
        Offline/tooling entry point. The live path compiles at dispatch through
        `compile_movements` directly - see `controller.compile_and_send`.
        :param initial_state: The keyboard state before compilation starts - held
            movement keys, typematic owner, and how long it has owned.
        """
        return compile_movements(
            initial_state,
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
            markerSize=3,
        )
        cv2.drawMarker(
            minimap_img,
            (end[0], end[1]),
            (255, 0, 0),
            markerType=cv2.MARKER_CROSS,
            markerSize=3,
        )
        for node in path:
            minimap_img[node.y, node.x] = (0, 255, 0)
        minimap_img = cv2.resize(minimap_img, None, fx=5, fy=5)
        cv2.imshow(
            f"_DEBUG_ Mode - Pathfinding {self.ign}2",
            minimap_img,
        )
        cv2.waitKey(1)
