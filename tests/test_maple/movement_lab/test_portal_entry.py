"""
A portal entry, replayed: its `up` keydowns land on the portal (#533).

**What the records showed** (Ellinia's `h_under00`, x 478, runs 28 to 32,
2026-11-15). The client takes a portal on an `up` keydown, a press or a
typematic repeat, made within its reach; `up` held down enters nothing. Every
recorded try fits that rule: no `up` keydown 22 px or more past the portal,
or 40 px or more short of it, entered; presses 4 and 10 px past it did. Three
ways of missing came back try after try:

- **`up` down from before, its keydowns silenced.** Cut at the Action
  duration cap on its way to the portal, a plan left `up` down; the next one
  pressed its walk's key after it, which took typematic, and a key down that
  does not own typematic repeats nothing (A7). Five tries walked through the
  portal so, `up` down all along, without one keydown.
- **A walk against the key still down.** Its key went down at once, the turn
  was not timed, and the `up` keydowns went 29 to 66 px short of the portal,
  three times.
- **A read older than the walk.** On run 32, read 0.34 and 0.38 s before the
  keys, the character had walked past the portal by the time they went down,
  and the `up` keydowns came 22 to 41 px past it: the first try of both of
  that run's retried portals.

**The rule.** The walk into a portal presses `up` again when it is down but
would not own typematic (`movement_mechanics_v2._press_up_again`); a walk into
a portal against a held key is a reversal (`_reversal`); a walk into a portal,
its key down, shorter than the read's lead turns back (`_turn_back`).

**The simulated character** walks along a flat floor, in virtual px from the
portal: a direction key down accelerates it at `walk_acceleration` to the walk
speed; the key up, or the other key down while it still moves this way, slows
it at `walk_deceleration`. It starts where its frame was read, moving as the
record's reads did, with the record's keys down, and walks on until the plan's
keys go down `AGE` s later. Its limits: exact reads, the plans' own physics,
no slope. It reproduces each of the records' 33 tries planned on the portal's
floor, entered or not, under any reach the records allow; whether the client's
turn and slide are the plans' is for a live Trial.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from maple.model.navigation import PORTAL_TIME
from tests.test_maple.movement_lab import corpus

#: The runs' physics: the game files' at speed 100%, the walk Calibration
#: constant 1.19 (the records' header).
PHYSICS = VRPhysics.from_game_files(
    corpus.LAB_PHYSICS_VALUES, calibration=Calibration(walk=1.19)
)
#: Virtual px from the portal within which an `up` keydown is taken to enter
#: it: the farthest press the records saw enter (run 32, 4 and 10 px past).
#: The client's reach is not in the game data; the records bound it only
#: between 10 and 22 px past the portal, and short of 40 px before it.
REACH = 10.0
#: The Action duration cap the runs compiled against (`TrialRunner`).
ACTION_DURATION = 1.0
#: Seconds from a key's send to the client acting on it.
LATENCIES = [0.0, 0.03]
_STEP = 0.0005


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(533)


@dataclass
class _Walker:
    """A character on a flat floor (the module docstring says how)."""

    x: float
    vx: float
    held: set[str]
    latency: float = 0.0
    t: float = 0.0
    #: Where the character was at each `up` keydown, as the client acted on it.
    ups: list[float] = field(default_factory=list[float])

    def run(self, until: float) -> None:
        while self.t < until:
            way = ("right" in self.held) - ("left" in self.held)
            if way and self.vx * way >= 0:
                speed = abs(self.vx) + PHYSICS.walk_acceleration * _STEP
                self.vx = way * min(PHYSICS.walk_speed, speed)
            elif way:
                self.vx += way * PHYSICS.walk_deceleration * _STEP
            else:
                slower = abs(self.vx) - PHYSICS.walk_deceleration * _STEP
                self.vx = math.copysign(max(0.0, slower), self.vx)
            self.x += self.vx * _STEP
            self.t += _STEP

    def play(self, sequence: KeyboardInputWrapper) -> None:
        at = self.t
        for keys, events, delay in zip(
            sequence.keys, sequence.events, sequence.delays, strict=True
        ):
            self.run(at + self.latency)
            keys = keys if isinstance(keys, list) else [keys]
            events = events if isinstance(events, list) else [events] * len(keys)
            for key, event in zip(keys, events, strict=True):
                if event == "keyup":
                    self.held.discard(key)
                    continue
                if key == "up":
                    self.ups.append(self.x)
                self.held.add(key)
            at += delay + OVERHEAD
        self.run(at + self.latency)


_PORTAL = _MovementComponent(MovementTypes.ENTER_PORTAL, 0.0, duration=PORTAL_TIME)
_END = _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0.0)
#: The walk after the portal, on its far side: on a miss, it runs on this one.
_AFTER = _MovementComponent(MovementTypes.WALK_RIGHT, 55.5)


@dataclass(frozen=True)
class _Try:
    """A recorded try: the read, the character's motion then, and the plan's walk."""

    x: float
    vx: float
    held: frozenset[str]
    owner: str | None
    age: float
    walk: MovementTypes
    length: float


#: Each kind of try the records hold, as read (x from the portal, px/s, the
#: keys down, the key owning typematic, the read's age at the keys).
TRIES = {
    "from the jump's landing, its key down (run 30 new-2 c13)": _Try(
        -74.1, 148.75, frozenset({"right"}), None, 0.13, MovementTypes.WALK_RIGHT, 74.1
    ),
    "read older than the walk (run 32 C1 try 1)": _Try(
        -28.7, 148.75, frozenset({"right"}), None, 0.34, MovementTypes.WALK_RIGHT, 28.7
    ),
    "read older than the walk (run 32 C2 try 1)": _Try(
        -35.0, 148.75, frozenset({"right"}), None, 0.38, MovementTypes.WALK_RIGHT, 35.0
    ),
    "against the key still down (run 28 base-1 c21)": _Try(
        69.1, 148.75, frozenset({"right"}), None, 0.14, MovementTypes.WALK_LEFT, 69.1
    ),
    "against the key still down, near (run 28 base-1 c22)": _Try(
        17.9, 148.75, frozenset({"right"}), "right", 0.13, MovementTypes.WALK_LEFT, 17.9
    ),
    "up down from before, the walk's key pressed after it (run 28 base-1 c20)": _Try(
        -69.6, 102.0, frozenset({"up"}), None, 0.13, MovementTypes.WALK_RIGHT, 69.6
    ),
    "up down from before, sliding past (run 32 C2 try 2)": _Try(
        -2.6, -143.0, frozenset({"up"}), None, 0.14, MovementTypes.WALK_RIGHT, 2.6
    ),
    "up down and owning typematic, its walk's key down (run 32 C1 try 3)": _Try(
        51.6,
        -148.75,
        frozenset({"left", "up"}),
        "up",
        0.13,
        MovementTypes.WALK_LEFT,
        51.6,
    ),
}


def _compile(
    plan: tuple[_MovementComponent, ...],
    held: frozenset[str],
    owner: str | None,
    age: float,
) -> KeyboardInputWrapper:
    sequence = compile_movements(
        InputState(held, owner, 1.0),
        movements=plan,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=PHYSICS.walk_speed,
        total_duration=ACTION_DURATION,
        walk_acceleration=PHYSICS.walk_acceleration,
        walk_deceleration=PHYSICS.walk_deceleration,
        read_at=0.0,
        clock=lambda: age,
    )
    assert sequence is not None
    return sequence


@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("name", list(TRIES))
def test_an_up_keydown_lands_on_the_portal(name: str, latency: float) -> None:
    attempt = TRIES[name]
    walker = _Walker(attempt.x, attempt.vx, set(attempt.held), latency)
    walker.run(attempt.age)
    sequence = _compile(
        (
            _MovementComponent(attempt.walk, attempt.length),
            _PORTAL,
            _AFTER,
            _END,
        ),
        attempt.held,
        attempt.owner,
        attempt.age,
    )

    walker.play(sequence)

    assert any(abs(x) <= REACH for x in walker.ups), [round(x) for x in walker.ups]


# --- the compile's rule ------------------------------------------------------------


def _steps(sequence: KeyboardInputWrapper) -> list[tuple[float, str, str]]:
    """Each key event with the time it is sent, seconds into the sequence."""
    at, steps = 0.0, []
    for keys, events, delay in zip(
        sequence.keys, sequence.events, sequence.delays, strict=True
    ):
        keys = keys if isinstance(keys, list) else [keys]
        events = events if isinstance(events, list) else [events] * len(keys)
        steps += [(at, k, e) for k, e in zip(keys, events, strict=True)]
        at += delay + OVERHEAD
    return steps


def _walk_into_portal(
    way: MovementTypes, length: float
) -> tuple[_MovementComponent, ...]:
    return (_MovementComponent(way, length), _PORTAL, _END)


def test_an_up_held_from_before_is_pressed_again_after_the_walks_key() -> None:
    sequence = _compile(
        _walk_into_portal(MovementTypes.WALK_RIGHT, 60.0), frozenset({"up"}), None, 0.13
    )
    steps = _steps(sequence)

    release = steps.index(next(s for s in steps if s[1:] == ("up", "keyup")))
    walk = steps.index(next(s for s in steps if s[1:] == ("right", "keydown")))
    press = steps.index(next(s for s in steps[release:] if s[1:] == ("up", "keydown")))
    assert release < press
    # `up` goes down no earlier than the walk's key, so it owns typematic.
    assert walk <= press


def test_an_up_owning_typematic_its_walks_key_down_is_left_alone() -> None:
    # Every such held `up` of the records entered on the walk's repeats.
    sequence = _compile(
        _walk_into_portal(MovementTypes.WALK_LEFT, 50.0),
        frozenset({"left", "up"}),
        "up",
        0.13,
    )
    steps = _steps(sequence)

    first_up_release = next(
        (t for t, k, e in steps if (k, e) == ("up", "keyup")), math.inf
    )
    repeats = [t for t, k, e in steps if (k, e) == ("up", "keydown")]
    assert repeats
    assert repeats[-1] < first_up_release


def test_a_walk_into_a_portal_against_the_held_key_waits_out_the_slide() -> None:
    sequence = _compile(
        _walk_into_portal(MovementTypes.WALK_LEFT, 40.0),
        frozenset({"right"}),
        None,
        0.13,
    )
    steps = _steps(sequence)

    assert steps[0][1:] == ("right", "keyup")
    walk = next(t for t, k, e in steps if (k, e) == ("left", "keydown"))
    assert walk >= PHYSICS.walk_speed / PHYSICS.walk_deceleration - 1e-9


def test_a_walk_into_a_portal_the_character_is_past_turns_back() -> None:
    # Read 0.34 s before the keys, `right` down: 50 px walked, the walk is 29.
    sequence = _compile(
        _walk_into_portal(MovementTypes.WALK_RIGHT, 28.7),
        frozenset({"right"}),
        None,
        0.34,
    )
    steps = _steps(sequence)

    assert steps[0][1:] == ("right", "keyup")
    assert not any((k, e) == ("right", "keydown") for _, k, e in steps)
    assert any((k, e) == ("left", "keydown") for _, k, e in steps)


def test_a_walk_into_a_portal_longer_than_the_lead_does_not_turn_back() -> None:
    sequence = _compile(
        _walk_into_portal(MovementTypes.WALK_RIGHT, 60.0),
        frozenset({"right"}),
        None,
        0.34,
    )

    assert not any(k == "left" for _, k, _ in _steps(sequence))
