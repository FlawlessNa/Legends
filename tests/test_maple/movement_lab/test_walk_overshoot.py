"""
The walk overshoot of #503, replayed: a simulated character walks the final
approaches of the first live walk Trials (Ellinia, speed and jump stats 1.0),
fed the Input Sequences `compile_movements` makes.

**What the record showed.** Long walks arrived fine, then the last Plan walked
70 to 90 virtual px past the target and the Trial corrected back and forth.
Three things add up to it, measured on the record (the PR has the table):

- the character walks while its position is read and the Plan compiled: the
  frame is 0.22 to 0.43 s old at the decision, plus about 0.05 s to dispatch,
  30 to 70 px at 149 px/s;
- the walk speed is 149 px/s, not the 125 the game files give: the walk
  Calibration constant is 1.19, not 1.0;
- the character slides on after the key comes up, about 14 px.

**The simulated character.** One dimension: a direction key down accelerates
it at `walkForce ÷ 100` to its top speed, the key up slows it at
`walkDrag ÷ 100` to a stop. Its top speed is the record's 149 px/s. The loop
around it is the Trial's: a frame is read `age` s after its capture (each
cycle's age from the record, the gap between a cycle's frame and the next
read's, less the 0.1 s decision interval), compiled `DISPATCH` s later, sent,
and the next frame is captured some time after the sequence ends: each
cycle's from the record (the read loop's own phase sets it, 0.01 to 0.4 s),
`GAP` after the record's cycles run out.

**Its limits.** The slide and the acceleration are the ones the fix is
computed from, so the replay cannot tell whether they are the client's: it
can only show the record's overshoot comes back from these numbers (it does,
to within 8 px), and that the fix removes it given them. Its reads are exact;
the live reads are a few px off, and their age varies cycle to cycle. Only a
live Trial checks the fix (#400 is the real acceptance).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD
from maple.model.mechanics.movement_mechanics_v2 import (
    _MAX_TRAVEL_LENGTH,
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from tests.test_maple.movement_lab import corpus

#: The walk speed the record measured: the median of 150 read-to-read speeds.
RECORD_WALK_SPEED = 149.0
#: The client's physics at speed 1.0: what the live run planned with.
AS_RUN = corpus.LAB_PHYSICS
#: The same, with the walk Calibration constant the record supports.
CALIBRATED = VRPhysics.from_game_files(
    corpus.LAB_PHYSICS_VALUES,
    calibration=Calibration(walk=RECORD_WALK_SPEED / AS_RUN.walk_speed),
)
#: Seconds from the decision to the compile; fitted to the four approaches.
DISPATCH = 0.05
#: Seconds from a sequence's end to the next decision's frame, past the
#: cycles the record has.
GAP = 0.15
#: The Trials' arrival tolerance, virtual px.
TOLERANCE = 16.0
#: The Action duration cap the Trials ran with (`TrialRunner`).
ACTION_DURATION = 1.0
_STEP = 0.0005


@dataclass
class _Character:
    """A character on a flat platform, walking at the record's top speed."""

    x: float
    v: float
    held: set[str] = field(default_factory=set[str])
    t: float = 0.0

    def run(self, until: float) -> None:
        accelerate = AS_RUN.walk_acceleration
        slow = AS_RUN.walk_deceleration
        while self.t < until:
            way = ("right" in self.held) - ("left" in self.held)
            if way and self.v * way >= 0:
                speed = min(RECORD_WALK_SPEED, abs(self.v) + accelerate * _STEP)
                self.v = way * speed
            elif way:
                # Turning: the key's force and the drag together.
                self.v += way * (accelerate + slow) * _STEP
            else:
                self.v = math.copysign(max(0.0, abs(self.v) - slow * _STEP), self.v)
            self.x += self.v * _STEP
            self.t += _STEP

    def play(self, sequence: KeyboardInputWrapper) -> None:
        """Each Step at its time in the send loop: the delays before it."""
        at = self.t
        for keys, events, delay in zip(
            sequence.keys, sequence.events, sequence.delays, strict=True
        ):
            self.run(at)
            keys = keys if isinstance(keys, list) else [keys]
            events = events if isinstance(events, list) else [events] * len(keys)
            for key, event in zip(keys, events, strict=True):
                if event == "keydown":
                    self.held.add(key)
                else:
                    self.held.discard(key)
            at += delay + OVERHEAD
        self.run(at)


def _plan(x: float, target: float) -> tuple[_MovementComponent, ...]:
    """A flat walk to `target`, cut into pieces as the planner cuts it."""
    length = abs(target - x)
    walk = MovementTypes.WALK_RIGHT if target > x else MovementTypes.WALK_LEFT
    pieces = max(1, math.ceil(length / _MAX_TRAVEL_LENGTH))
    return (_MovementComponent(walk, length / pieces),) * pieces + (
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0.0),
    )


@dataclass(frozen=True)
class _Approach:
    """One Trial's last cycles, from its last long walk, as the record has them."""

    name: str
    start: float
    target: float
    #: Each cycle's frame age at the decision, from the record.
    ages: tuple[float, ...]
    #: Each cycle's seconds from its sequence's end to the next frame.
    gaps: tuple[float, ...]
    #: How far the record walked past the target on the final approach.
    recorded_overshoot: float


#: walk-right-1 from cycle 10, walk-left-1 from 8, walk-right-2 from 10,
#: walk-left-2 from 8 (`.scratch/live_run1/walk_run.jsonl`).
APPROACHES = [
    _Approach("walk-right-1", 982.7, 1300.0, (0.40, 0.22, 0.22), (0.01, 0.19), 72.6),
    _Approach("walk-left-1", -135.0, -400.1, (0.39, 0.425, 0.43), (0.13, 0.33), 92.0),
    _Approach("walk-right-2", 1004.0, 1300.0, (0.40, 0.22, 0.22), (0.02, 0.05), 71.8),
    _Approach("walk-left-2", -149.0, -400.0, (0.39, 0.43, 0.40), (0.09, 0.40), 89.4),
]


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(503)


@dataclass
class _Replay:
    #: Signed error of each read, virtual px: past the target is positive.
    errors: list[float]
    #: The way each dispatched Plan walked: +1 towards the start's far side.
    plans: list[int]

    @property
    def overshoot(self) -> float:
        return max(0.0, *self.errors)

    @property
    def decisions_to_arrive(self) -> int:
        return len(self.plans)


def _replay(approach: _Approach, physics: VRPhysics, *, fixed: bool) -> _Replay:
    """
    The Trial's loop from its last long walk to arrival, the character
    walking at full speed towards the target with its key down.

    `fixed`: compile as `MovementsMixin` now does (the walk's dynamics and the
    read's time); otherwise as the live run did, a walk timed by its length.
    """
    way = 1 if approach.target > approach.start else -1
    key = "right" if way > 0 else "left"
    character = _Character(approach.start, way * RECORD_WALK_SPEED, {key})
    replay = _Replay([], [])
    frame = 0.0
    for cycle in range(10):
        character.run(frame)
        read = character.x
        replay.errors.append(way * (read - approach.target))
        if abs(read - approach.target) <= TOLERANCE:
            return replay
        compile_at = frame + approach.ages[min(cycle, len(approach.ages) - 1)]
        compile_at += DISPATCH
        character.run(compile_at)
        plan = _plan(read, approach.target)
        replay.plans.append(way if read < approach.target else -way)
        held = frozenset(k for k in character.held if k in ("left", "right"))
        timing: dict[str, object] = {}
        if fixed:
            timing = {
                "walk_acceleration": physics.walk_acceleration,
                "walk_deceleration": physics.walk_deceleration,
                "read_at": frame,
                "clock": lambda at=compile_at: at,
            }
        sequence = compile_movements(
            InputState(held, next(iter(held), None), 1.0),
            movements=plan,
            handle=corpus.LAB_HANDLE,
            ign=corpus.LAB_IGN,
            speed=physics.walk_speed,
            total_duration=ACTION_DURATION,
            **timing,  # pyright: ignore[reportArgumentType]
        )
        assert sequence is not None
        character.play(sequence)
        frame = character.t + (
            approach.gaps[cycle] if cycle < len(approach.gaps) else GAP
        )
    pytest.fail(f"{approach.name} never arrived: reads {replay.errors}")


# --- the record, reproduced --------------------------------------------------------


@pytest.mark.parametrize("approach", APPROACHES, ids=lambda a: a.name)
def test_the_replay_walks_past_the_target_as_the_record_did(
    approach: _Approach,
) -> None:
    replay = _replay(approach, AS_RUN, fixed=False)

    assert replay.overshoot == pytest.approx(approach.recorded_overshoot, abs=8.0)
    # Then the correction back the other way the record shows.
    assert -1 in replay.plans


# --- the fix -----------------------------------------------------------------------


@pytest.mark.parametrize("approach", APPROACHES, ids=lambda a: a.name)
def test_the_last_walk_stops_on_the_target_without_a_correction_back(
    approach: _Approach,
) -> None:
    replay = _replay(approach, CALIBRATED, fixed=True)

    # Within the Trial's tolerance, never tens of px past it.
    assert replay.overshoot <= TOLERANCE
    # The long walk's last Plan and at most one more, both the same way.
    assert replay.decisions_to_arrive <= 2
    assert -1 not in replay.plans


# --- the compile's rules -----------------------------------------------------------


def _release_time(sequence: KeyboardInputWrapper, key: str) -> float:
    """Seconds into the sequence at which `key` comes up."""
    at = 0.0
    for keys, events, delay in zip(
        sequence.keys, sequence.events, sequence.delays, strict=True
    ):
        keys = keys if isinstance(keys, list) else [keys]
        events = events if isinstance(events, list) else [events] * len(keys)
        if any(k == key and e == "keyup" for k, e in zip(keys, events, strict=True)):
            return at
        at += delay + OVERHEAD
    raise AssertionError(f"{key} never comes up")


def _compile(
    plan: tuple[_MovementComponent, ...],
    held: frozenset[str] = frozenset(),
    *,
    since_read: float | None = None,
    total_duration: float | None = None,
) -> KeyboardInputWrapper:
    sequence = compile_movements(
        InputState(held, next(iter(held), None), 1.0),
        movements=plan,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=CALIBRATED.walk_speed,
        total_duration=total_duration,
        walk_acceleration=CALIBRATED.walk_acceleration,
        walk_deceleration=CALIBRATED.walk_deceleration,
        read_at=None if since_read is None else 0.0,
        clock=lambda: since_read or 0.0,
    )
    assert sequence is not None
    return sequence


#: A walk one piece long: a fill overshoots its time by up to one typematic
#: repeat per piece, which a longer walk would add up.
_ONE_PIECE = 70.0
#: One typematic repeat and some: how near a release lands to its time.
_STEP_SLACK = 0.04


def test_a_walking_character_is_released_its_slide_early() -> None:
    sequence = _compile(_plan(0.0, _ONE_PIECE), frozenset({"right"}))

    assert _release_time(sequence, "right") == pytest.approx(
        CALIBRATED.walk_press_time(_ONE_PIECE, moving=True), abs=_STEP_SLACK
    )


def test_the_read_age_is_walked_off_only_when_the_key_is_down() -> None:
    held = _compile(_plan(0.0, _ONE_PIECE), frozenset({"right"}), since_read=0.2)
    from_rest = _compile(_plan(0.0, _ONE_PIECE), since_read=0.2)

    walked = CALIBRATED.walk_speed * 0.2
    assert _release_time(held, "right") == pytest.approx(
        CALIBRATED.walk_press_time(_ONE_PIECE - walked, moving=True),
        abs=_STEP_SLACK,
    )
    # Standing still, the character has not moved since the read.
    assert _release_time(from_rest, "right") == pytest.approx(
        CALIBRATED.walk_press_time(_ONE_PIECE, moving=False), abs=_STEP_SLACK
    )


def test_a_cut_too_near_the_stop_for_the_next_plan_finishes_the_walk() -> None:
    # From rest, so nothing is walked off: 1.2 s of key down. A cut at 1.0 s
    # leaves 0.2 s, less than the 0.4 s this plan's read took.
    physics = CALIBRATED
    ramp = physics.walk_speed**2 / (2 * physics.walk_acceleration)
    length = physics.walk_speed * 1.2 - ramp + physics.stop_slide
    plan = _plan(0.0, length)

    finished = _compile(plan, since_read=0.4, total_duration=1.0)
    no_read = _compile(plan, total_duration=1.0)
    early = _compile(plan, since_read=0.4, total_duration=0.5)

    assert "right" not in finished.keys_held
    assert _release_time(finished, "right") == pytest.approx(
        1.2, abs=_STEP_SLACK * len(plan)
    )
    # With no read time there is nothing to judge the next plan by: cut, held.
    assert "right" in no_read.keys_held
    # A cut far enough from the stop is a Continuation, as before.
    assert "right" in early.keys_held
