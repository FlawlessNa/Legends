"""
A vertical take-off the plan opens on, a direction key still down: led by the
read's age (#540).

**What the records showed** (runs 28 and 29, Ellinia, 2026-11-15, key times
from #538, the Session put on the record's clock by its key records). A plan
that opens on a jump straight up or a drop starts at the read. With a
direction key still down from the Action before (a Continuation), the
character walked on from the read until the compile, 115 to 340 ms, and slid
on after the release (#530's stand-still): all 12 such take-offs went down 28
to 55 px off their spot, the older the read the farther. Walked to, 16 of 17
vertical take-offs went down within 15 px. And a drop after a walk
against the held key (no reversal for a drop) went down 52 to 90 px off.

**The rule** (`movement_mechanics_v2._walk_back`, `_reversal`). Such a plan
compiles a walk back first, as a walk against a held key into the take-off
does: the key comes up, the slide is waited out, and the walk covers what the
character walked since the read plus the slide, from rest.

**The simulated character** is `test_chained_takeoff.py`'s, on the flat
stretch of `fixture_maps.step_up`'s floor (no slope effect on speed). The
jump key's press is the take-off, a drop's as well (it does not model the
fall through). Every key acts `latency` after its send, the first release
too, so the character walks that much more before it slides: the take-off is
judged within the walk speed times the latency.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pytest

from botting.controller import NO_COMPONENT, InputState, KeyboardInputWrapper
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.world import Platform, WorldMap
from tests.test_maple.movement_lab import corpus, fixture_maps
from tests.test_maple.movement_lab.conftest import JUMP_KEY
from tests.test_maple.movement_lab.test_chained_takeoff import (
    LATENCIES,
    _Character,
    _steps,
)
from tests.test_maple.movement_lab.test_standing_jump import PHYSICS, STOP

#: The two read ages of the records: a fused read (115 to 135 ms from capture
#: to compile) and a slow one (290 to 340 ms).
AGES = [0.13, 0.33]
#: Where the plans take off, on the floor's flat-enough middle.
X0 = 0.0
#: Px past the latency's walk a take-off may be: the walk's last repeat runs
#: up to one Step past its time, and the simulation steps 0.5 ms.
SLACK = 2.0

#: Px a walk from rest loses to its acceleration: `speed² ÷ 2 acceleration`.
_ACCELERATION_COST = PHYSICS.walk_speed**2 / (2 * PHYSICS.walk_acceleration)

_END = _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0.0)


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(540)


@pytest.fixture(scope="module")
def floor() -> Platform:
    world = WorldMap.from_map_data(fixture_maps.step_up())
    return world.platforms[0]


@dataclass
class _Watched(_Character):
    """The character, with where each jump key found it."""

    jumps: list[tuple[float, float]] = field(default_factory=list[tuple[float, float]])

    def _press(self, key: str, event: str, planned: Platform | None) -> None:
        if key == JUMP_KEY and event == "keydown" and key not in self.held:
            self.jumps.append((self.x, self.vx))
        super()._press(key, event, planned)


def _takeoff(
    kind: MovementTypes, floor: Platform, *, x: float = X0
) -> _MovementComponent:
    y = floor.y_at(x)
    assert y is not None
    duration = 0.327 if kind is MovementTypes.JUMP else 0.3
    return _MovementComponent(kind, 0.0, duration=duration, start=(x, y), end=(x, y))


def _compile(
    plan: tuple[_MovementComponent, ...], held: frozenset[str], age: float
) -> KeyboardInputWrapper:
    sequence = compile_movements(
        InputState(held, next(iter(sorted(held)), None), 1.0),
        movements=plan,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=PHYSICS.walk_speed,
        walk_acceleration=PHYSICS.walk_acceleration,
        walk_deceleration=PHYSICS.walk_deceleration,
        read_at=0.0,
        clock=lambda: age,
    )
    assert sequence is not None
    return sequence


def _run(
    floor: Platform,
    plan: tuple[_MovementComponent, ...],
    key: str,
    *,
    age: float,
    latency: float,
) -> tuple[float, float]:
    """
    The plan, read at `X0` with `key` down and the character walking its way
    at the walk speed, compiled `age` later: where its first jump key found
    the character, and its sideways speed then.
    """
    y = floor.y_at(X0)
    assert y is not None
    way = 1 if key == "right" else -1
    character = _Watched(
        (floor,),
        X0,
        y,
        floor,
        PHYSICS,
        latency,
        way * PHYSICS.walk_speed,
        held={key},
    )
    character.run(age)
    character.play(_compile(plan, frozenset({key}), age), lambda origin: None)
    assert character.jumps, "no jump key went down"
    return character.jumps[0]


_VERTICAL = {
    "a jump straight up": MovementTypes.JUMP,
    "a drop": MovementTypes.JUMP_DOWN,
}


@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("age", AGES)
@pytest.mark.parametrize("key", ["left", "right"])
@pytest.mark.parametrize("kind", list(_VERTICAL), ids=list(_VERTICAL))
def test_a_vertical_take_off_the_plan_opens_on_goes_down_on_its_spot(
    floor: Platform, kind: str, key: str, age: float, latency: float
) -> None:
    takeoff = _VERTICAL[kind]
    plan = (_takeoff(takeoff, floor), _END)

    x, vx = _run(floor, plan, key, age=age, latency=latency)

    # Px past the spot the way the character was walking: the latency's walk
    # before the release acts is the only part left unled. A drop is walked
    # into from rest, so it may also fall short of the walk back by the
    # acceleration's cost, as a walk after a reversal does (#521).
    past = (x - X0) * (1 if key == "right" else -1)
    cost = 0.0 if takeoff is MovementTypes.JUMP else _ACCELERATION_COST
    assert -SLACK <= past <= PHYSICS.walk_speed * latency + cost + SLACK
    if takeoff is MovementTypes.JUMP:
        # Still standing still as it goes (#530).
        assert abs(vx) < 1.0


@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("age", AGES)
def test_a_drop_walked_to_against_the_held_key_goes_down_on_its_spot(
    floor: Platform, age: float, latency: float
) -> None:
    # Read at X0 walking right; the drop is 40 px left of it.
    walk = _MovementComponent(MovementTypes.WALK_LEFT, 40.0)
    plan = (walk, _takeoff(MovementTypes.JUMP_DOWN, floor, x=X0 - 40.0), _END)

    x, _ = _run(floor, plan, "right", age=age, latency=latency)

    # Px short of the drop, the way the walk goes: walked into from rest after
    # the turn, short by the acceleration's cost at most, as a sideways jump
    # after a reversal is (#521), and by the latency's walk the wrong way.
    short = x - (X0 - 40.0)
    assert -SLACK <= short <= PHYSICS.walk_speed * latency + _ACCELERATION_COST + SLACK


def test_the_walk_back_keeps_each_steps_plan_component(floor: Platform) -> None:
    # Provenance: the walk back serves the take-off (component 0), and the
    # walk after it is still component 1, as the key records name them (#538).
    plan = (
        _takeoff(MovementTypes.JUMP, floor),
        _MovementComponent(MovementTypes.WALK_RIGHT, 147.0),
        _END,
    )
    sequence = _compile(plan, frozenset({"right"}), 0.13)

    steps = list(zip(_steps(sequence), sequence.origins, strict=True))
    jump = next(
        i for i, ((_, k, e), _) in enumerate(steps) if (k, e) == (JUMP_KEY, "keydown")
    )
    assert {origin for _, origin in steps[: jump + 1]} == {0}
    # The plan's closing release carries the sentinel, as every plan's does.
    assert {origin for _, origin in steps[jump + 1 :]} <= {0, 1, NO_COMPONENT}
    assert any(
        origin == 1 for (_, k, e), origin in steps if (k, e) == ("right", "keydown")
    )


@pytest.mark.parametrize(
    ("first", "held"),
    [
        pytest.param(MovementTypes.JUMP_LEFT, frozenset({"right"}), id="sideways"),
        pytest.param(MovementTypes.JUMP, frozenset({"right", "up"}), id="on a rope"),
        pytest.param(MovementTypes.JUMP_DOWN, frozenset(), id="no key down"),
    ],
)
def test_no_walk_back_where_the_rule_does_not_reach(
    floor: Platform, first: MovementTypes, held: frozenset[str]
) -> None:
    takeoff = (
        _MovementComponent(first, 60.0, duration=0.4, start=(X0, 0.0), end=(X0, 0.0))
        if first is MovementTypes.JUMP_LEFT
        else _takeoff(first, floor)
    )
    sequence = _compile((takeoff, _END), held, 0.33)

    steps = _steps(sequence)
    jump = next(t for t, k, e in steps if (k, e) == (JUMP_KEY, "keydown"))
    if first is MovementTypes.JUMP_LEFT:
        # Its own direction goes down with the jump, sooner than a release
        # and its slide could pass.
        assert jump < STOP
        return
    walked = [
        k
        for t, k, e in steps
        if t < jump and e == "keydown" and k in {"left", "right"} - held
    ]
    assert walked == []


#: #560's 5 tries (runs 30, 31 and 36): a plan that opens on a walk its key down,
#: shorter than the read's lead, into a jump straight up. The walk's length and
#: the read's age at the compile, as the records have them. Each was keyed 34 to
#: 56 px past its spot, and missed.
_SHORT_WALKS = [
    pytest.param(2.1, 0.115, id="run 36 c40"),
    pytest.param(0.5, 0.114, id="run 36 c43"),
    pytest.param(0.1, 0.119, id="run 36 c46"),
    pytest.param(4.3, 0.134, id="run 30 c13"),
    pytest.param(22.8, 0.345, id="run 31 c106"),
]


@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("key", ["left", "right"])
@pytest.mark.parametrize(("length", "age"), _SHORT_WALKS)
def test_a_walk_shorter_than_the_lead_into_a_jump_up_turns_back_to_its_spot(
    floor: Platform, length: float, age: float, key: str, latency: float
) -> None:
    """
    #560: the walk was shortened to nothing (`_time_walks`), its key came up,
    the slide was waited out and the jump went down: past the spot by what the
    character walked since the read plus the slide. It turns back instead, as a
    walk into a portal the character has passed does (`_turn_back`): timed from
    rest, from where the character is at the compile.
    """
    way = 1 if key == "right" else -1
    spot = X0 + way * length
    walk = MovementTypes.WALK_RIGHT if key == "right" else MovementTypes.WALK_LEFT
    plan = (
        _MovementComponent(walk, length),
        _takeoff(MovementTypes.JUMP, floor, x=spot),
        _END,
    )

    x, vx = _run(floor, plan, key, age=age, latency=latency)

    # Px past the spot the way the character was walking: as for the jump up
    # the plan opens on, the latency's walk before the release acts is unled.
    past = (x - spot) * way
    assert -SLACK <= past <= PHYSICS.walk_speed * latency + SLACK
    assert abs(vx) < 1.0


@pytest.mark.parametrize("key", ["left", "right"])
@pytest.mark.parametrize(
    "length",
    [
        pytest.param(21.0, id="past the lead by less than the slide"),
        pytest.param(60.0, id="past the lead and the slide"),
    ],
)
def test_a_walk_longer_than_the_lead_into_a_jump_up_does_not_turn_back(
    floor: Platform, key: str, length: float
) -> None:
    """
    Read 0.13 s before the compile: 19 px walked, and 14 more to slide. A walk
    of 21 px still stops past its spot, by up to the slide, as before: no record
    has that shape, so it is not turned back until a live run shows it (#560).
    """
    walk = MovementTypes.WALK_RIGHT if key == "right" else MovementTypes.WALK_LEFT
    way = 1 if key == "right" else -1
    plan = (
        _MovementComponent(walk, length),
        _takeoff(MovementTypes.JUMP, floor, x=X0 + way * length),
        _END,
    )
    sequence = _compile(plan, frozenset({key}), 0.13)

    other = "left" if key == "right" else "right"
    assert not any(k == other for _, k, _ in _steps(sequence))
