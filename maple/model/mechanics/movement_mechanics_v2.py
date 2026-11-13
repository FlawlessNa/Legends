"""
Movement Plans in virtual px, and their compilation into Input Sequences.

`MovementHandler` plans a `Path` on the map's `FootholdGraph`, from the
character's virtual position to a virtual target (`compute_path`), and turns
its moves into a Movement Plan (`path_into_movements`): one component per
move, except that consecutive walks (and consecutive climbs) the same way are
one component, cut into pieces of at most `_MAX_TRAVEL_LENGTH`.
`compile_movements` compiles a Movement Plan into an Input Sequence, at
dispatch (ADR 0002).

**Units.** A component's `length` is in virtual px. A walk or a climb lasts its
length at the physics' walk or climb speed; every other move lasts what the
graph says it takes (`_MovementComponent.duration`): a jump its flight, a drop
its fall, a portal its planning time. No compile time is a fixed number of
seconds of its own.

**Where a walk stops** (#503). Given the walk's acceleration and deceleration,
`compile_movements` times two walks by where the character comes to rest
rather than by length alone (`_time_walks`): the plan's last walk, which ends
in a key release, stops short by the slide after the release; and a first walk
whose key is already down is shortened by how far the character has walked
since the frame its position was read on (`read_at`), up to the moment of
compiling.

**Which graph moves become which component.**

- `WALK` left or right: `WALK_LEFT`/`WALK_RIGHT`, its length along x. A walk
  across a join adds nothing.
- `FALL` off a platform's end: the walk the same way, since the direction is
  held through the fall. Its length is its drift, `|landing x - take-off x|`,
  which is the walk speed times the fall's time.
- `FALL` off a rope's bottom: `CLIMB_DOWN`, its length the drop, lasting the
  fall's time.
- `CLIMB` up or down: `CLIMB_UP`/`CLIMB_DOWN`, its length along y.
- `JUMP` left, right or up: `JUMP_LEFT`/`JUMP_RIGHT`/`JUMP`, lasting its flight;
  `grabs_rope` when it ends on a rope.
- `DROP`: `JUMP_DOWN`, lasting its fall.
- `TELEPORT`: `TELEPORT_*`; consecutive teleports the same way are one
  component of that many `casts`, as the teleport builder casts them.
- `PORTAL`: `ENTER_PORTAL`.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Sequence
from enum import IntEnum
from functools import lru_cache
from itertools import pairwise
from typing import TYPE_CHECKING, Literal, NamedTuple

from botting import PARENT_LOG
from botting.controller import (
    EVENTS,
    NO_COMPONENT,
    InputState,
    KeyboardInputWrapper,
    get_held_movement_keys,
    key_binds,
)
from game_data.catalogue import Rope
from maple.actions import movements_v2
from maple.model.characters.maple_skills import MapleSkill
from maple.model.navigation.moves import Direction as MoveDirection
from maple.model.navigation.moves import Move, MoveKind, Path, Point
from maple.model.world import Platform

from .physics import walk_press_time, walk_stop_slide

if TYPE_CHECKING:
    from maple.model.navigation.foothold_graph import FootholdGraph
    from maple.model.navigation.foothold_graphs import FootholdGraphs
    from maple.model.world import WorldMap

    from .physics import VRPhysics

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


#: Virtual px a walk or a climb component may be at most: a longer one is cut
#: into equal pieces. Was `_MAX_WALK_SIZE`, 5 minimap px; at 16 virtual px per
#: minimap px (every MSCW minimap, `mag` 4) that is 80.
_MAX_TRAVEL_LENGTH = 80.0

#: Platforms this narrow (virtual px, right end minus left end) get a
#: direction-stop after a jump or teleport lands on them. Was 5 minimap px;
#: at 16 virtual px each that is 80. The default only: `MovementHandler` carries
#: its own, so a Trial batch can sweep it as a Knob without touching
#: production's value.
_NARROW_PLATFORM_THRESHOLD = 80.0

#: A jump or teleport that takes off this close (virtual px) to its platform's
#: end, in the travel direction, gets the edge-departure flag (PM3). Was 5
#: minimap px, 80 virtual px. Same shape as the threshold above: module default
#: only, `MovementHandler` carries its own per-instance value.
_EDGE_DEPARTURE_THRESHOLD = 80.0

_PRECISION_PRE_STOP = frozenset(
    {
        MovementTypes.JUMP,
        MovementTypes.JUMP_LEFT,
        MovementTypes.JUMP_RIGHT,
        MovementTypes.JUMP_DOWN,
        MovementTypes.ENTER_PORTAL,
    }
)

_JUMPS = frozenset(
    {
        MovementTypes.JUMP,
        MovementTypes.JUMP_LEFT,
        MovementTypes.JUMP_RIGHT,
        MovementTypes.JUMP_DOWN,
    }
)

_CLIMBS = frozenset({MovementTypes.CLIMB_UP, MovementTypes.CLIMB_DOWN})

_TELEPORTS = frozenset(
    {
        MovementTypes.TELEPORT_LEFT,
        MovementTypes.TELEPORT_RIGHT,
        MovementTypes.TELEPORT_UP,
        MovementTypes.TELEPORT_DOWN,
    }
)

#: Walks: the moves the walk's acceleration and slide apply to.
_WALKS = frozenset({MovementTypes.WALK_LEFT, MovementTypes.WALK_RIGHT})

#: Components that are travel along a surface: merged and cut by length.
_TRAVEL = _WALKS | _CLIMBS

# Landing width (PM2) applies to any jump, drop or teleport that lands on a platform.
_NARROW_KINDS = frozenset({MoveKind.JUMP, MoveKind.DROP, MoveKind.TELEPORT})

# Edge departure (PM3) only has a "travel direction" sense for horizontal gestures -
# a platform has a left/right end, not an up/down one.
_EDGE_DEPARTURE_KINDS = frozenset({MoveKind.JUMP, MoveKind.TELEPORT})

_SIDEWAYS = {
    MoveDirection.LEFT: "LEFT",
    MoveDirection.RIGHT: "RIGHT",
    MoveDirection.UP: "UP",
    MoveDirection.DOWN: "DOWN",
}


class _MovementComponent(NamedTuple):
    """
    One component of a Movement Plan.

    :ivar length: Virtual px: along x for a walk (a fall's drift included) and
        for a jump or a sideways teleport, along y for a climb, a fall off a
        rope and an up or down teleport; 0 for a jump straight up, a drop and
        a portal.
    :ivar narrow: This jump, drop or teleport lands on a platform at most
        `narrow_platform_threshold` virtual px wide.
    :ivar edge_departure: This sideways jump or teleport takes off within
        `edge_departure_threshold` virtual px of its platform's end, in the
        travel direction.
    :ivar duration: Seconds it lasts, when that is not its length at the
        physics' speed: a jump's flight (to its landing, or to the rope it
        grabs), a drop's or a fall's time, a portal's planning time. `None`
        for a walk or a climb.
    :ivar grabs_rope: This jump ends on a rope.
    :ivar casts: How many teleports, back to back, a `TELEPORT_*` component is;
        1 for every other component.
    :ivar start: Where it takes off, virtual px; `None` for a plan built by
        hand.
    :ivar end: Where it ends, likewise.
    """

    movement_type: MovementTypes
    length: float
    narrow: bool = False
    edge_departure: bool = False
    duration: float | None = None
    grabs_rope: bool = False
    casts: int = 1
    start: Point | None = None
    end: Point | None = None


def _flight(move: _MovementComponent) -> float:
    """
    The seconds a jump's keys are held for: its flight, as the graph traced it.

    :raises ValueError: The component carries none. A jump's hold is never a
        fixed number of seconds.
    """
    if move.duration is None:
        raise ValueError(
            f"{move.movement_type.name} has no duration: a jump lasts its flight, "
            f"which its Movement Plan component carries from the graph's move"
        )
    return move.duration


def compile_movements(
    initial_state: InputState | None,
    *,
    movements: tuple[_MovementComponent, ...],
    handle: int,
    ign: str,
    speed: float,
    climb_speed: float | None = None,
    teleport: MapleSkill | None = None,
    total_duration: float | None = None,
    always_release: bool = False,
    walk_acceleration: float = math.inf,
    walk_deceleration: float = math.inf,
    read_at: float | None = None,
    clock: Callable[[], float] = time.monotonic,
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
    :param speed: The walk speed, virtual px/s (`VRPhysics.walk_speed`): a walk
        lasts its length at it.
    :param climb_speed: The climb speed, virtual px/s (`VRPhysics.climb_speed`);
        `speed` when not given.
    :param total_duration: When given, compilation stops once the sequence reaches it.
    :param always_release: Force-release every key still held at the end of the
        sequence. This is the flag form of what `_always_release_keys_on_actions`
        used to do by post-processing a compiled Action in the Engine process.
    :param walk_acceleration: Virtual px/s² from rest (`VRPhysics`). With
        `walk_deceleration`, it times the first and last walks by where the
        character stops (`_time_walks`); both infinite (the default), a walk
        lasts its length at `speed`.
    :param walk_deceleration: Virtual px/s² sliding to a stop (`VRPhysics`).
    :param read_at: When the frame the plan's start was read on was captured,
        on `clock`. The character has walked since, when the first walk's key
        is already down. `None`: no lead.
    :param clock: The frames' clock, `time.monotonic`; a test passes its own.
    :return: The Input Sequence, or None when the plan compiles to nothing.
    :raises ValueError: A jump carries no `duration`, a drop grabs a rope, or a
        teleport is planned with no teleport skill.
    """
    climb = speed if climb_speed is None else climb_speed
    since_read = None if read_at is None else max(0.0, clock() - read_at)
    if since_read is not None or not (
        math.isinf(walk_acceleration) and math.isinf(walk_deceleration)
    ):
        movements = _time_walks(
            movements,
            _held_keys(handle, initial_state),
            since_read=since_read,
            speed=speed,
            acceleration=walk_acceleration,
            deceleration=walk_deceleration,
        )
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
        move_type = move.movement_type
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
                    duration=(
                        move.length / speed if move.duration is None else move.duration
                    ),
                    structure=structure,
                    release_keys=release_keys,
                    initial_state=initial_state,
                )

            case MovementTypes.CLIMB_UP | MovementTypes.CLIMB_DOWN:
                direction = _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                secondary = None
                # A climb carries the next walk's direction, so the character steps
                # off the rope's end straight into it. A fall off a rope's bottom
                # (a climb with a duration) does not: held in the air, the
                # direction would carry it sideways off its landing.
                if move.duration is None:
                    if upcoming_move.movement_type is MovementTypes.WALK_LEFT:
                        secondary = "left"
                    elif upcoming_move.movement_type is MovementTypes.WALK_RIGHT:
                        secondary = "right"
                # TODO - See if duration needs to be extended
                structure = movements_v2.move(
                    handle,
                    direction,
                    secondary,
                    duration=(
                        move.length / climb if move.duration is None else move.duration
                    ),
                    structure=structure,
                    initial_state=initial_state,
                )

            case (
                MovementTypes.JUMP | MovementTypes.JUMP_LEFT | MovementTypes.JUMP_RIGHT
            ):
                jump_key = key_binds(ign)["jump"]
                flight = _flight(move)
                if move.grabs_rope and move_type is MovementTypes.JUMP:
                    # Straight up into a rope's bottom (#111): its own shape, which
                    # holds `up` into the climb.
                    structure = movements_v2.jump_up_on_rope(
                        handle,
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                        duration=flight,
                    )
                elif move.grabs_rope:
                    side: Literal["left", "right"] = (
                        "left" if move_type is MovementTypes.JUMP_LEFT else "right"
                    )
                    structure = movements_v2.jump_on_rope(
                        handle,
                        side,
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                        duration=flight,
                    )
                else:
                    direction = (
                        "up"
                        if move_type is MovementTypes.JUMP
                        else _DIRECTIONS[move_type.name.split("_")[-1].lower()]
                    )
                    structure = movements_v2.single_jump(
                        handle,
                        direction,
                        jump_key,
                        structure=structure,
                        initial_state=initial_state,
                        duration=flight,
                    )
                    structure = _narrow_stop(structure, move)

            case MovementTypes.JUMP_DOWN:
                if move.grabs_rope:
                    raise ValueError(
                        "JUMP_DOWN grabs a rope: a drop lands on a platform only"
                    )
                jump_key = key_binds(ign)["jump"]
                structure = movements_v2.single_jump(
                    handle,
                    "down",
                    jump_key,
                    structure=structure,
                    initial_state=initial_state,
                    duration=_flight(move),
                )
                structure = _narrow_stop(structure, move)

            case MovementTypes.ENTER_PORTAL:
                structure = movements_v2.move(
                    handle,
                    "up",
                    duration=(
                        move.length / speed if move.duration is None else move.duration
                    ),
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
                    move.casts,
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
        if (
            total_duration is not None
            and structure.duration >= total_duration
            and not _finish_instead_of_cut(
                movements,
                origin,
                structure.duration - total_duration,
                since_read,
                walk_stop_slide(speed, walk_deceleration) / speed,
            )
        ):
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


def _held_keys(handle: int, initial_state: InputState | None) -> set[str]:
    """The movement keys down as the sequence starts, as `movements_v2` reads them."""
    if initial_state is not None:
        return set(initial_state.held_keys)
    return set(get_held_movement_keys(handle))


def _walk_run(movements: Sequence[_MovementComponent], start: int, step: int) -> range:
    """
    The indices of the walks the same way as `movements[start]`, from `start`
    on, forwards (`step` 1) or backwards (-1): one walk the planner cut into
    pieces. Empty when `movements[start]` is no walk.
    """
    first = movements[start]
    if first.movement_type not in _WALKS:
        return range(start, start)
    end = start
    while (
        0 <= end + step < len(movements)
        and movements[end + step].movement_type is first.movement_type
    ):
        end += step
    return range(min(start, end), max(start, end) + 1)


def _time_walks(
    movements: tuple[_MovementComponent, ...],
    held_keys: set[str],
    *,
    since_read: float | None,
    speed: float,
    acceleration: float,
    deceleration: float,
) -> tuple[_MovementComponent, ...]:
    """
    The plan, with its first and last walks timed by where the character
    comes to rest (#503), as a `duration` on each of their pieces.

    - **The last walk**, which the sequence's final release ends, holds its
      key only until the slide after the release carries the character the
      rest of the way (`walk_press_time`).
    - **The first walk, its key already down** (a Continuation): the character
      has walked at `speed` from the frame its position was read on until now,
      `since_read` seconds, so that much less is left to walk. Without it, a
      plan compiled from a read 0.2 to 0.4 s old walks 30 to 60 px past its
      end (the live record of #503).

    When the first walk is also the last, both apply. The last walk starts
    from rest only when it is the plan's first move and its key is up; after
    any other move it counts as moving, which errs short, by at most the
    acceleration's cost (`speed² ÷ 2 acceleration`), rather than long.

    Every other component is left as it was: a walk lasting its length at
    `speed`.
    """
    if len(movements) < 2:
        return movements
    timed = list(movements)
    first = _walk_run(movements, 0, 1)
    held = bool(first) and _direction_of(movements[0]) in held_keys
    lead = speed * since_read if held and since_read is not None else 0.0
    # The END_OF_MOVEMENT sentinel closes every plan: the last move is before it.
    last = _walk_run(movements, len(movements) - 2, -1)

    def length(run: range) -> float:
        return sum(movements[i].length for i in run)

    def spread(run: range, seconds: float) -> None:
        total = length(run)
        for i in run:
            share = movements[i].length / total if total > 0 else 1 / len(run)
            timed[i] = movements[i]._replace(duration=seconds * share)

    def press(distance: float, *, moving: bool) -> float:
        return walk_press_time(
            distance,
            speed=speed,
            acceleration=acceleration,
            deceleration=deceleration,
            moving=moving,
        )

    if first and first == last:
        spread(first, press(length(first) - lead, moving=held))
        return tuple(timed)
    if first and held:
        spread(first, max(0.0, length(first) - lead) / speed)
    if last:
        spread(last, press(length(last), moving=last.start > 0 or held))
    return tuple(timed)


def _finish_instead_of_cut(
    movements: tuple[_MovementComponent, ...],
    origin: int,
    overrun: float,
    since_read: float | None,
    slide_time: float,
) -> bool:
    """
    Whether to compile the plan to its end rather than cut it at the Action
    duration cap, because the cut lands in its last walk too near the stop for
    the next plan to make it (#503).

    A cut leaves the direction key down (a Continuation), and the next plan
    can release it only once the next position is read and compiled: about
    `since_read` seconds, what this plan's own read took. If less of the last
    walk is left after the cut than that, plus the slide's worth of walk
    (`slide_time`), the character walks past the target before anything can
    stop it: the live record walked 60 to 70 px past it that way. Finishing
    the walk here instead stops it where `_time_walks` timed it to.

    :param origin: The component being compiled when the cap was reached.
    :param overrun: Seconds the sequence runs past the cap so far.
    """
    if since_read is None:
        return False
    last = _walk_run(movements, len(movements) - 2, -1)
    if origin not in last:
        return False
    left = overrun + sum(movements[i].duration or 0.0 for i in last if i > origin)
    return left < since_read + slide_time


def _direction_of(move: _MovementComponent) -> str:
    """The direction key a walk holds."""
    return _DIRECTIONS[move.movement_type.name.split("_")[-1].lower()]


def _narrow_stop(
    structure: KeyboardInputWrapper, move: _MovementComponent
) -> KeyboardInputWrapper:
    """
    Narrow platform: release the horizontal key on landing so the character
    doesn't walk off the edge after touching down.
    """
    if move.narrow:
        held_dir = next(
            (k for k in structure.keys_held if k in ("left", "right")),
            None,
        )
        if held_dir:
            structure.append(held_dir, "keyup", 0)
    return structure


class MovementHandler:
    """
    Plans Paths on a map's `FootholdGraph` and turns them into Movement Plans.

    **The graph follows the character's stats.** Its jump ranges and times
    depend on the jump arc, so the graph is built per `VRPhysics`: a path is
    planned on the graph of the physics it is asked with. A change of speed or
    jump stat is a new `VRPhysics`, and the next Path is planned on its graph.

    **The graphs are built off the decision loop** (`FootholdGraphs`, #430).
    `ready_graph` never blocks: while the graph of the current physics builds,
    it returns `None` and the live planner holds. `graph` and `compute_path`
    block until the graph is built, for offline callers.
    """

    _CACHE_MAXSIZE = 256  # bounded: plans for stale positions age out

    def __init__(
        self,
        handle: int,
        world_map: WorldMap,
        ign: str,
        teleport: MapleSkill | None = None,
        *,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
        graphs: FootholdGraphs | None = None,
    ) -> None:
        """
        :param world_map: The map the paths are planned on.
        :param teleport: The character's teleport skill: with it, the graph
            holds teleport moves.
        :param narrow_platform_threshold: Platform width (virtual px) at or
            below which a jump, drop or teleport onto it is marked `narrow`, so
            compilation adds the landing direction-stop. `None` is the module
            default, which is what production wants. It is per-instance because
            it is a **Knob** a Trial batch sweeps (`maple.calibration.specs.Knobs`),
            and it shapes the Movement Plan here, in the Engine -
            `compile_movements` reads the component's `narrow` flag and never the
            threshold, so the send path is untouched.
        :param edge_departure_threshold: Distance (virtual px) from a platform's
            end, in the travel direction, within which a jump or teleport's
            take-off is marked `edge_departure`, so compilation adds the
            pre-departure stop. Same shape as `narrow_platform_threshold`: `None`
            is the module default, per-instance because it is a Knob, and read by
            `compile_movements` only through the component's `edge_departure` flag.
        :param graphs: The map's graphs, shared with the other handlers of the
            Bot so a graph is built once however many DecisionMakers plan
            (`BotData.foothold_graphs`). `None` keeps graphs of its own.
        :raises ValueError: `graphs` are another map's, or disagree with
            `teleport`.
        """
        # Imported here: `maple.model.navigation` imports this package's
        # `physics`, so a module-level import would be circular.
        from maple.model.navigation.foothold_graphs import FootholdGraphs

        if graphs is None:
            graphs = FootholdGraphs(world_map, teleport=teleport is not None)
        elif graphs.world_map is not world_map or graphs.teleport != (
            teleport is not None
        ):
            raise ValueError(
                "the graphs given are another map's, or disagree on teleport"
            )
        self.graphs = graphs
        self.handle = handle
        self.world_map = world_map
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
        # Per-instance, bounded caches: an `@lru_cache` on the method itself would key
        # on `self`, pinning every handler ever created in memory for the process
        # lifetime. Binding the cache here scopes it to this instance, so it's freed
        # when the handler is.
        self._compute_path = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._compute_path_uncached
        )
        self.path_into_movements = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._path_into_movements_uncached
        )

    def graph(self, physics: VRPhysics) -> FootholdGraph:
        """The graph of `physics`; blocks until it is built (offline callers)."""
        return self.graphs.graph(physics)

    def ready_graph(self, physics: VRPhysics) -> FootholdGraph | None:
        """
        The graph of `physics` if it is built; otherwise `None`, and it is
        built off the caller's thread. Never blocks on a build.
        """
        return self.graphs.ready(physics)

    def compute_path(
        self,
        start: Point,
        goal: Point,
        physics: VRPhysics,
        *,
        graph: FootholdGraph | None = None,
    ) -> Path | None:
        """
        The quickest Path from `start` to `goal`, in virtual px, on the graph of
        `physics`.

        :param graph: That graph, as `ready_graph` returned it: the live
            planner passes it, so the Path is planned on it even if it has
            since been dropped from the kept graphs. `None` blocks until the
            graph of `physics` is built (offline callers).
        :return: `None` when no path joins them, or when either lies on no
            platform or rope (the character in the air, say): the caller plans
            again from its next position.
        """
        return self._compute_path(
            (float(start[0]), float(start[1])),
            (float(goal[0]), float(goal[1])),
            physics,
            graph,
        )

    def _compute_path_uncached(
        self,
        start: Point,
        goal: Point,
        physics: VRPhysics,
        graph: FootholdGraph | None,
    ) -> Path | None:
        # Per-cycle pathing traces, so DEBUG is the honest level.
        logger.debug("Computing path from %s to %s", start, goal)
        if graph is None:
            graph = self.graph(physics)
        try:
            return graph.path(start, goal)
        except ValueError as error:
            logger.debug("No path: %s", error)
            return None

    def _path_into_movements_uncached(
        self, path: Path | None
    ) -> tuple[_MovementComponent, ...]:
        """
        The Movement Plan of `path`, ending with the `END_OF_MOVEMENT` sentinel;
        empty for no path.
        """
        if path is None:
            return ()
        components = [self._component(move) for move in path.moves]
        logger.debug("Movements: %s", components)
        plan = _cut(_merge(components))
        plan.append(_MovementComponent(MovementTypes.END_OF_MOVEMENT, 0))
        return tuple(plan)

    def _component(self, move: Move) -> _MovementComponent:
        dx = abs(move.end[0] - move.start[0])
        dy = abs(move.end[1] - move.start[1])
        side = _SIDEWAYS[move.direction] if move.direction is not None else None
        match move.kind:
            case MoveKind.WALK:
                return self._travel(MovementTypes[f"WALK_{side}"], dx, move)
            case MoveKind.FALL if move.direction is MoveDirection.DOWN:
                return _MovementComponent(
                    MovementTypes.CLIMB_DOWN,
                    dy,
                    duration=move.duration,
                    start=move.start,
                    end=move.end,
                )
            case MoveKind.FALL:
                return self._travel(MovementTypes[f"WALK_{side}"], dx, move)
            case MoveKind.CLIMB:
                return self._travel(MovementTypes[f"CLIMB_{side}"], dy, move)
            case MoveKind.JUMP:
                name = "JUMP" if move.direction is MoveDirection.UP else f"JUMP_{side}"
                return self._gesture(
                    MovementTypes[name],
                    dx,
                    move,
                    grabs_rope=isinstance(move.end_on, Rope),
                )
            case MoveKind.DROP:
                return self._gesture(MovementTypes.JUMP_DOWN, dx, move)
            case MoveKind.TELEPORT:
                return self._gesture(
                    MovementTypes[f"TELEPORT_{side}"],
                    dy if side in ("UP", "DOWN") else dx,
                    move,
                    timed=False,
                )
            case MoveKind.PORTAL:
                return _MovementComponent(
                    MovementTypes.ENTER_PORTAL,
                    0.0,
                    duration=move.duration,
                    start=move.start,
                    end=move.end,
                )
        raise NotImplementedError(f"Unhandled graph move {move.kind!r}")

    def _travel(
        self, movement_type: MovementTypes, length: float, move: Move
    ) -> _MovementComponent:
        return _MovementComponent(movement_type, length, start=move.start, end=move.end)

    def _gesture(
        self,
        movement_type: MovementTypes,
        length: float,
        move: Move,
        *,
        grabs_rope: bool = False,
        timed: bool = True,
    ) -> _MovementComponent:
        """A jump, a drop or a teleport, with its precision flags."""
        narrow = (
            move.kind in _NARROW_KINDS
            and isinstance(move.end_on, Platform)
            and move.end_on.right - move.end_on.left <= self.narrow_platform_threshold
        )
        edge_departure = False
        if move.kind in _EDGE_DEPARTURE_KINDS and isinstance(move.start_on, Platform):
            if move.direction is MoveDirection.RIGHT:
                edge_departure = (
                    move.start_on.right - move.start[0] <= self.edge_departure_threshold
                )
            elif move.direction is MoveDirection.LEFT:
                edge_departure = (
                    move.start[0] - move.start_on.left <= self.edge_departure_threshold
                )
        return _MovementComponent(
            movement_type,
            length,
            narrow=narrow,
            edge_departure=edge_departure,
            duration=move.duration if timed else None,
            grabs_rope=grabs_rope,
            start=move.start,
            end=move.end,
        )

    def movements_into_action(
        self,
        movements: tuple[_MovementComponent, ...],
        physics: VRPhysics,
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
            speed=physics.walk_speed,
            climb_speed=physics.climb_speed,
            teleport=self.teleport,
            total_duration=total_duration,
        )


def _merge(components: list[_MovementComponent]) -> list[_MovementComponent]:
    """
    Consecutive walks the same way are one walk, whichever platforms they
    cross, and consecutive climbs the same way one climb; a walk of no length
    (across a join) is dropped once merged. A component with a duration of its
    own (a fall off a rope's bottom) merges with nothing. Consecutive teleports
    the same way are one component of that many casts: it departs from the
    first's take-off (`edge_departure`) and lands where the last lands
    (`narrow`).
    """
    merged: list[_MovementComponent] = []
    for component in components:
        last = merged[-1] if merged else None
        if (
            last is not None
            and component.movement_type in _TELEPORTS
            and last.movement_type is component.movement_type
        ):
            merged[-1] = last._replace(
                length=last.length + component.length,
                casts=last.casts + component.casts,
                narrow=component.narrow,
                end=component.end,
            )
        elif (
            last is not None
            and component.movement_type in _TRAVEL
            and last.movement_type is component.movement_type
            and last.duration is None
            and component.duration is None
        ):
            merged[-1] = last._replace(
                length=last.length + component.length, end=component.end
            )
        else:
            merged.append(component)
    walks = _TRAVEL - _CLIMBS
    return [c for c in merged if c.movement_type not in walks or c.length > 0]


def _cut(components: list[_MovementComponent]) -> list[_MovementComponent]:
    """
    Each walk or climb longer than `_MAX_TRAVEL_LENGTH` cut into the fewest
    equal pieces no longer than it, each with its share of the take-off and
    landing (interpolated along the straight line between them).
    """
    cut: list[_MovementComponent] = []
    for component in components:
        if (
            component.movement_type not in _TRAVEL
            or component.duration is not None
            or component.length <= _MAX_TRAVEL_LENGTH
        ):
            cut.append(component)
            continue
        pieces = math.ceil(component.length / _MAX_TRAVEL_LENGTH)
        for k in range(pieces):
            cut.append(
                component._replace(
                    length=component.length / pieces,
                    start=_between(component.start, component.end, k / pieces),
                    end=_between(component.start, component.end, (k + 1) / pieces),
                )
            )
    return cut


def _between(a: Point | None, b: Point | None, share: float) -> Point | None:
    if a is None or b is None:
        return None
    return (a[0] + (b[0] - a[0]) * share, a[1] + (b[1] - a[1]) * share)
