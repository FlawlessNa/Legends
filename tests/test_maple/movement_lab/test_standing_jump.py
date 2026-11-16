"""
A jump straight up, replayed: it goes down standing still (#530).

**What the record showed** (`bottom-to-real-top-1`, Ellinia, 2026-11-14,
cycles 33 to 48). The last climb, from the second-highest platform onto the
highest, was planned seven times the same way: walk left to x -113, `JUMP` up
(length 0), walk right to the target. The graph traces that jump with no
sideways speed, from the one end of the stretch it reaches the platform from.
But the compile kept the walk's direction key down into the jump, so the client
carried the walk's speed into the air: each of the seven took off at 130 to
223 px/s, and six missed.

- Arriving walking left (cycles 34, 39, 45), the take-off was 3 to 7 px from
  its point, but the jump flew about 45 px left, onto the platform near its
  open left end, and walked off it with the key still down; once (cycle 45) a
  plan read in the air turned it around in time.
- Arriving walking right, after such a fall, the walk left pressed its key at
  once, the turn was not timed, and the jump took off 55 to 61 px early
  (cycles 36, 42), under a part of the platform too high to reach.
- Read walking right at the take-off (cycles 37, 43), the 0.8 px walk was
  already behind the character, and the jump flew right with `right` down,
  under the platform's high part.

**The rule.** Before a jump straight up off a platform, the direction key
comes up and the jump key waits out the slide (`speed ÷ deceleration`); the
walk into it is timed to come to rest on the take-off, from rest after a
reversal (`movement_mechanics_v2._stand_still`, `_time_walks`).

**The simulated character** is `test_chained_takeoff.py`'s: on the jump key,
it leaves with the walk speed the way a direction key is down, or with its own
speed when none is, as the record's jumps did. Its limits are that module's:
exact reads, fixed latencies, the plans' own physics, no slope effect on speed.
Whether the client's standing jump rises as high as the graph's arc is for a
live Trial: the jump constant is the slowest jump fitted (0.96), so the arc
errs low.
"""

from __future__ import annotations

import random

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from maple.model.navigation import TAKEOFF_STEP, Point
from maple.model.world import WorldMap
from tests.test_maple.movement_lab import corpus, fixture_maps
from tests.test_maple.movement_lab.conftest import JUMP_KEY
from tests.test_maple.movement_lab.test_chained_takeoff import (
    LATENCIES,
    _replay,
    _steps,
)

#: The real-top climb's physics: the game files' at speed 100%, and the
#: record's Calibration constants (its header).
CLIMB_BATCH = Calibration(walk=1.19, jump=0.96, climb=0.95)
PHYSICS = VRPhysics.from_game_files(corpus.LAB_PHYSICS_VALUES, calibration=CLIMB_BATCH)
#: Seconds the character slides to rest from the walk speed.
STOP = PHYSICS.walk_speed / PHYSICS.walk_deceleration
#: Seconds from a frame's capture to its plan's keys: the record's cycles 33
#: to 48 (0.13 to 0.17 above an unknown base).
AGE = 0.14
#: The sideways speed, px/s, below which the character counts as standing.
STANDING = 1.0


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(530)


# --- the compile's rule ------------------------------------------------------------

_END = _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0.0)
_UP = _MovementComponent(MovementTypes.JUMP, 0.0, duration=0.327)


def _walk(way: MovementTypes, length: float) -> _MovementComponent:
    return _MovementComponent(way, length)


def _compile(
    plan: tuple[_MovementComponent, ...], held: frozenset[str]
) -> KeyboardInputWrapper:
    sequence = compile_movements(
        InputState(held, next(iter(held), None), 1.0),
        movements=plan,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=PHYSICS.walk_speed,
        walk_acceleration=PHYSICS.walk_acceleration,
        walk_deceleration=PHYSICS.walk_deceleration,
        read_at=0.0,
        clock=lambda: AGE,
    )
    assert sequence is not None
    return sequence


#: Each shape of the record's straight-up jumps: the plan, and the direction
#: key down as it was compiled.
SHAPES = {
    "walked into, its key down (cycle 34)": (
        (_walk(MovementTypes.WALK_LEFT, 122.4), _UP, _END),
        frozenset({"left"}),
    ),
    "walked into from rest": (
        (_walk(MovementTypes.WALK_LEFT, 40.0), _UP, _END),
        frozenset(),
    ),
    "walked into against the other key (cycle 36)": (
        (_walk(MovementTypes.WALK_LEFT, 40.1), _UP, _END),
        frozenset({"right"}),
    ),
    "a walk shorter than the read's lead (cycle 37)": (
        (
            _walk(MovementTypes.WALK_RIGHT, 0.8),
            _UP,
            _walk(MovementTypes.WALK_RIGHT, 147.0),
            _END,
        ),
        frozenset({"right"}),
    ),
    "first, a key still down (cycle 11)": (
        (_UP, _walk(MovementTypes.WALK_LEFT, 0.8), _END),
        frozenset({"right"}),
    ),
}


def _held_at(
    sequence: KeyboardInputWrapper, held: frozenset[str], at: float
) -> set[str]:
    down = set(held)
    for t, key, event in _steps(sequence):
        if t > at:
            break
        if event == "keydown":
            down.add(key)
        else:
            down.discard(key)
    return down


@pytest.mark.parametrize("shape", list(SHAPES))
def test_a_jump_straight_up_goes_down_standing_still(shape: str) -> None:
    plan, held = SHAPES[shape]
    sequence = _compile(plan, held)
    steps = _steps(sequence)

    jump = next(t for t, k, e in steps if (k, e) == (JUMP_KEY, "keydown"))
    # No direction key down as the jump key goes down,
    assert not _held_at(sequence, held, jump) & {"left", "right"}
    # and the last one came up a whole slide before it.
    releases = [
        t for t, k, e in steps if k in ("left", "right") and e == "keyup" and t <= jump
    ]
    assert releases
    assert jump - releases[-1] >= STOP - 1e-9


def test_the_walk_into_it_comes_to_rest_on_its_take_off() -> None:
    sequence = _compile((_walk(MovementTypes.WALK_LEFT, 60.0), _UP, _END), frozenset())

    release = next(t for t, k, e in _steps(sequence) if (k, e) == ("left", "keyup"))
    # Held as long as the slide after it leaves to walk, from rest: a walk's
    # last repeat runs up to one Step past its time.
    expected = PHYSICS.walk_press_time(60.0, moving=False)
    assert expected <= release <= expected + TAKEOFF_STEP


def test_a_sideways_jump_walked_into_still_keeps_its_key() -> None:
    # The rule is for a jump straight up only: a sideways one takes off walking.
    jump = _MovementComponent(MovementTypes.JUMP_LEFT, 60.0, duration=0.4)
    sequence = _compile(
        (_walk(MovementTypes.WALK_LEFT, 40.0), jump, _END), frozenset({"left"})
    )

    press = next(t for t, k, e in _steps(sequence) if (k, e) == (JUMP_KEY, "keydown"))
    assert "left" in _held_at(sequence, frozenset({"left"}), press)


# --- the climb, replayed ------------------------------------------------------------

#: On the synthetic map's highest part, where the record's target was.
GOAL: Point = (100.0, -107.6)


@pytest.fixture(scope="module")
def step_up() -> WorldMap:
    """The record's last climb, on a synthetic map (`fixture_maps.step_up`)."""
    return WorldMap.from_map_data(fixture_maps.step_up())


def test_the_path_is_the_records_jump_straight_up(step_up: WorldMap) -> None:
    handler = MovementHandler(corpus.LAB_HANDLE, step_up, corpus.LAB_IGN)
    path = handler.compute_path((100.0, 40.0), GOAL, PHYSICS)

    assert path is not None
    assert [(m.kind.value, m.direction and m.direction.value) for m in path.moves] == [
        ("walk", "left"),
        ("jump", "up"),
        ("walk", "right"),
    ]


#: Where each replay starts, and how the character moves there: the record's
#: three ways of arriving at the take-off (x -99 here), at the walk speed with
#: its key down, and standing.
ARRIVALS = {
    "walking left to it": [(0.0, "left"), (60.0, "left"), (120.0, "left")],
    "walking right, past it": [(-60.0, "right"), (-20.0, "right")],
    "walking right, at it": [(-110.0, "right"), (-100.0, "right")],
    "standing": [(40.0, None), (-99.0, None)],
}
_CASES = [
    pytest.param(x, key, id=f"{name}, x {x:.0f}")
    for name, starts in ARRIVALS.items()
    for x, key in starts
]


@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize(("start_x", "key"), _CASES)
def test_every_jump_up_takes_off_standing_and_the_climb_arrives(
    step_up: WorldMap, start_x: float, key: str | None, latency: float
) -> None:
    floor = step_up.platforms[0]
    y = floor.y_at(start_x)
    assert y is not None
    way = {"left": -1, "right": 1, None: 0}[key]

    replay = _replay(
        step_up,
        (start_x, y),
        GOAL,
        latency=latency,
        held=frozenset({key}) if key else frozenset(),
        vx=way * PHYSICS.walk_speed,
        physics=PHYSICS,
    )

    assert replay.arrived
    assert replay.presses
    assert all(replay.where_planned)
    assert all(abs(p.vx) < STANDING for p in replay.presses)


# --- the record's seven attempts, on Ellinia ----------------------------------------

#: Each attempt's cycle: its read, and the direction key down then, the
#: character walking that way at the walk speed.
REAL_TOP = {
    "cycle 34": ((9.3, -4040.8), "left"),
    "cycle 36": ((-72.9, -4062.0), "right"),
    "cycle 37": ((-113.8, -4076.6), "right"),
    "cycle 39": ((20.8, -4035.3), "left"),
    "cycle 42": ((-64.2, -4058.9), "right"),
    "cycle 43": ((-116.2, -4077.0), "right"),
    "cycle 45": ((14.2, -4037.3), "left"),
}


@pytest.mark.client_files
@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("cycle", list(REAL_TOP))
def test_the_real_top_climbs_attempts_arrive_standing(
    cycle: str, latency: float
) -> None:
    world = WorldMap.load("Victoria Road: Ellinia")
    physics = VRPhysics.load(calibration=CLIMB_BATCH)
    start, key = REAL_TOP[cycle]
    way = 1 if key == "right" else -1

    replay = _replay(
        world,
        start,
        (34.0, -4185.5),
        latency=latency,
        held=frozenset({key}),
        vx=way * physics.walk_speed,
        physics=physics,
    )

    assert replay.arrived
    assert replay.presses
    assert all(replay.where_planned)
    assert all(abs(p.vx) < STANDING for p in replay.presses)
