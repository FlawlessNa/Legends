"""
The chained jump of #515, replayed: a simulated character runs a Path of two
jumps with a short walk between, the second off a narrow ledge's open end,
fed the Input Sequences `compile_movements` makes, with the record's read
latency between plans.

**What the record showed** (`gap-right-1`, Ellinia, 2026-11-14). The first
jump of the chain landed; the second never took off, twice:

- cycle 9 planned it from a platform's open end exactly, the one point that
  jump lands from. The edge departure's release came straight back up one
  input delay later (33 ms), and the jump key one delay after that: the
  character, still walking, was past the end by then (`TAKEOFF_STEP`);
- cycle 10, planned from the ledge it fell onto, with the walk key still down
  from the cut at the Action duration cap, read the character 22 px from that
  ledge's open end. The plan's keys went down 0.25 s after the cut and
  0.13 s after the read, and the jump key found the character in the air.

**The simulated character.** It stands on the map's platforms, in virtual px:
a direction key down accelerates it at `walk_acceleration` to the walk speed,
the key up slows it at `walk_deceleration`; past a platform's end it falls
under `gravity`, at most `fall_speed`. The jump key, on a platform, sends it
up at `jump_speed` and sideways at the walk speed the way a direction key is
down (or at its speed, with none). The jump key in the air does nothing. Its
physics are the live run's: speed 100%, the walk Calibration constant 1.19.

**The loop around it** is the Trial's: a frame is read `AGE` s after its
capture and compiled then, with `read_at`; the next frame is captured `GAP` s
after the sequence ends. A frame captured in the air plans nothing (the
planner places no start in the air), and the next is captured one `READ`
later. Both latencies are the record's, from cycle 9's cut to cycle 10's keys.

**Its limits.** Its reads are exact and its latencies fixed; the live reads
are a few px off, and their age varies cycle to cycle. Its physics are the
ones the plans are made from, so it cannot tell whether those are the
client's: the walk, the arc and the slide are taken as the graph and the
compile take them. It has no ropes, no slopes' effect on speed, and a jump
in it takes off at the walk speed even from rest, which the client's
standing jumps are not known to do. It shows the compile now presses each
jump key while the character is on its platform, and the record's way of
failing comes back without the fix; only a live Trial checks the fix
(`gap-right-1`).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from maple.model.navigation import TAKEOFF_STEP, Point
from maple.model.world import Platform, WorldMap
from tests.test_maple.movement_lab import corpus, fixture_maps
from tests.test_maple.movement_lab.conftest import JUMP_KEY

#: The physics of the live run: the game files' at speed 100%, the walk
#: Calibration constant 1.19 (the record's header).
PHYSICS = VRPhysics.from_game_files(
    corpus.LAB_PHYSICS_VALUES, calibration=Calibration(walk=1.19)
)
#: Seconds from a frame's capture to its plan's compile: cycle 10's.
AGE = 0.13
#: Seconds from a sequence's end to the next frame's capture: from cycle 9's
#: cut to cycle 10's frame.
GAP = 0.137
#: Seconds between two frames when one plans nothing: the reads' median gap.
READ = 0.12
#: The Action duration cap the Trials ran with (`TrialRunner`).
ACTION_DURATION = 1.0
#: The Trials' arrival tolerance, virtual px.
TOLERANCE = 16.0
_STEP = 0.0005


#: Where the replay goes: well inside the platform.
GOAL: Point = (480.0, -52.0)


@dataclass
class _Character:
    """A character on the map's platforms (the module docstring says how)."""

    platforms: tuple[Platform, ...]
    x: float
    y: float
    on: Platform | None
    vx: float = 0.0
    vy: float = 0.0
    held: set[str] = field(default_factory=set[str])
    t: float = 0.0
    #: Each jump key press: whether the character was on a platform.
    presses: list[bool] = field(default_factory=list[bool])

    def _surface(self, x: float, top: float, bottom: float) -> Platform | None:
        """The highest platform at `x` between heights `top` and `bottom`."""
        found = [
            (y, p)
            for p in self.platforms
            if (y := p.y_at(x)) is not None and top - 0.5 <= y <= bottom + 0.5
        ]
        return min(found, key=lambda pair: pair[0])[1] if found else None

    def run(self, until: float) -> None:
        while self.t < until:
            if self.on is not None:
                self._walk()
            else:
                self._fly()
            self.t += _STEP

    def _walk(self) -> None:
        assert self.on is not None
        way = ("right" in self.held) - ("left" in self.held)
        if way and self.vx * way >= 0:
            speed = abs(self.vx) + PHYSICS.walk_acceleration * _STEP
            self.vx = way * min(PHYSICS.walk_speed, speed)
        elif way:
            self.vx += (
                way * (PHYSICS.walk_acceleration + PHYSICS.walk_deceleration) * _STEP
            )
        else:
            slower = abs(self.vx) - PHYSICS.walk_deceleration * _STEP
            self.vx = math.copysign(max(0.0, slower), self.vx)
        self.x += self.vx * _STEP
        y = self.on.y_at(self.x)
        if y is not None:
            self.y = y
            return
        self.on = self._surface(self.x, self.y - 1, self.y + 1)
        self.vy = 0.0

    def _fly(self) -> None:
        top = self.y
        self.vy = min(self.vy + PHYSICS.gravity * _STEP, PHYSICS.fall_speed)
        self.x += self.vx * _STEP
        self.y += self.vy * _STEP
        if self.vy > 0 and (landing := self._surface(self.x, top, self.y)):
            self.on = landing
            self.y = landing.y_at(self.x) or self.y
            self.vy = 0.0

    def _press(self, key: str, event: str) -> None:
        if event == "keyup":
            self.held.discard(key)
            return
        if key == JUMP_KEY and key not in self.held:
            self.presses.append(self.on is not None)
            if self.on is not None:
                way = ("right" in self.held) - ("left" in self.held)
                self.vx = way * PHYSICS.walk_speed if way else self.vx
                self.vy = -PHYSICS.jump_speed
                self.on = None
        self.held.add(key)

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
                self._press(key, event)
            at += delay + OVERHEAD
        self.run(at)


@dataclass
class _Replay:
    arrived: bool
    #: Each jump key press: whether the character was on a platform.
    presses: list[bool]
    #: How many plans were dispatched.
    plans: int


def _replay(world: WorldMap, start_x: float, goal: Point) -> _Replay:
    """The Trial's loop from a standstill at `start_x` on the floor."""
    handler = MovementHandler(corpus.LAB_HANDLE, world, corpus.LAB_IGN)
    floor = world.platform_at((start_x, 0.0))
    assert isinstance(floor, Platform)
    character = _Character(world.platforms, start_x, 0.0, floor)
    frame, plans = 0.0, 0
    for _ in range(12):
        character.run(frame)
        read = (character.x, character.y)
        if math.dist(read, goal) <= TOLERANCE and character.on is not None:
            return _Replay(True, character.presses, plans)
        path = handler.compute_path(read, goal, PHYSICS) if character.on else None
        plan = handler.path_into_movements(path)
        if len(plan) < 2:
            frame += READ
            continue
        compile_at = frame + AGE
        character.run(compile_at)
        held = frozenset(k for k in character.held if k in ("left", "right"))
        sequence = compile_movements(
            InputState(held, next(iter(held), None), 1.0),
            movements=plan,
            handle=corpus.LAB_HANDLE,
            ign=corpus.LAB_IGN,
            speed=PHYSICS.walk_speed,
            total_duration=ACTION_DURATION,
            walk_acceleration=PHYSICS.walk_acceleration,
            walk_deceleration=PHYSICS.walk_deceleration,
            read_at=frame,
            clock=lambda at=compile_at: at,
        )
        assert sequence is not None
        plans += 1
        character.play(sequence)
        frame = character.t + GAP
    return _Replay(False, character.presses, plans)


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(515)


@pytest.fixture(scope="module")
def world() -> WorldMap:
    """The record's chain, on a synthetic map (`fixture_maps.ledge_chain`)."""
    return WorldMap.from_map_data(fixture_maps.ledge_chain())


# --- the chain, replayed -------------------------------------------------------------

#: Starts on the floor, from a standstill, 20 px apart: wherever the Action
#: duration cap lands in the chain.
STARTS = [float(x) for x in range(20, 200, 20)]


@pytest.mark.parametrize("start_x", STARTS)
def test_every_jump_key_of_the_chain_goes_down_on_a_platform(
    world: WorldMap, start_x: float
) -> None:
    replay = _replay(world, start_x, GOAL)

    assert replay.arrived
    # Both jumps, and no jump key pressed in the air.
    assert replay.presses == [True, True]


def test_the_path_takes_off_inside_both_open_ends(world: WorldMap) -> None:
    handler = MovementHandler(corpus.LAB_HANDLE, world, corpus.LAB_IGN)
    path = handler.compute_path((40.0, 0.0), GOAL, PHYSICS)

    assert path is not None
    jumps = [m for m in path.moves if m.kind.name == "JUMP"]
    assert len(jumps) == 2
    margin = PHYSICS.walk_speed * TAKEOFF_STEP
    for jump in jumps:
        assert isinstance(jump.start_on, Platform)
        assert jump.start_on.right - jump.start[0] >= margin - 1e-6


# --- the compile's rules -------------------------------------------------------------

_LEAD = 0.13


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


def _compile(
    plan: tuple[_MovementComponent, ...],
    held: frozenset[str] = frozenset(),
    *,
    total_duration: float | None = None,
    since_read: float | None = None,
) -> KeyboardInputWrapper:
    # The keys held, as after a landing: the jump key took typematic from them.
    sequence = compile_movements(
        InputState(held, None, 1.0),
        movements=plan,
        handle=corpus.LAB_HANDLE,
        ign=corpus.LAB_IGN,
        speed=PHYSICS.walk_speed,
        total_duration=total_duration,
        read_at=None if since_read is None else 0.0,
        clock=lambda: since_read or 0.0,
    )
    assert sequence is not None
    return sequence


def _jump(
    way: MovementTypes, *, edge: bool = True, narrow: bool = False, rope: bool = False
) -> _MovementComponent:
    return _MovementComponent(
        way, 70.0, narrow=narrow, edge_departure=edge, duration=0.5, grabs_rope=rope
    )


_END = _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0.0)
_WALK = _MovementComponent(MovementTypes.WALK_RIGHT, 30.0)


def _press_time(sequence: KeyboardInputWrapper, key: str = JUMP_KEY) -> float:
    return next(t for t, k, e in _steps(sequence) if (k, e) == (key, "keydown"))


@pytest.mark.parametrize("rope", [False, True], ids=["platform", "rope"])
def test_a_jump_walked_into_presses_its_key_as_the_walk_ends(rope: bool) -> None:
    # The character walks right, the key down, into a jump right off an edge.
    sequence = _compile(
        (_WALK, _jump(MovementTypes.JUMP_RIGHT, rope=rope), _END),
        frozenset({"right"}),
    )

    walk = _WALK.length / PHYSICS.walk_speed
    # Within the Step that ends the walk: no input delay after it.
    assert _press_time(sequence) == pytest.approx(walk, abs=OVERHEAD * 2)
    # `right` stays down from the walk into the jump: no release between.
    assert ("right", "keyup") not in [
        (k, e) for t, k, e in _steps(sequence) if t <= _press_time(sequence)
    ]


def test_an_edge_jump_the_other_way_still_stops_the_walk_first() -> None:
    sequence = _compile(
        (_WALK, _jump(MovementTypes.JUMP_LEFT), _END), frozenset({"right"})
    )

    releases = [t for t, k, e in _steps(sequence) if (k, e) == ("right", "keyup")]
    assert releases
    assert releases[0] <= _press_time(sequence)


def test_a_narrow_landing_the_plan_walks_on_from_keeps_its_key_down() -> None:
    narrow = _jump(MovementTypes.JUMP_RIGHT, edge=False, narrow=True)
    walked_on = _compile((narrow, _WALK, _END))
    stopped = _compile((narrow, _END))

    landing = 0.5
    downs = [(k, e) for t, k, e in _steps(walked_on) if t < landing + 0.1]
    assert ("right", "keyup") not in downs
    # With nothing after it, the narrow landing's stop is as before: on landing.
    release = next(t for t, k, e in _steps(stopped) if (k, e) == ("right", "keyup"))
    assert release == pytest.approx(landing, abs=0.1)


def _chain(walk_after: float) -> tuple[_MovementComponent, ...]:
    """
    A jump right, a walk right of `walk_after` px, an edge jump right, and a
    walk right long enough to be cut (#503 finishes a short last walk).
    """
    first = _jump(MovementTypes.JUMP_RIGHT, edge=False)
    after = _MovementComponent(MovementTypes.WALK_RIGHT, walk_after)
    last = _MovementComponent(MovementTypes.WALK_RIGHT, PHYSICS.walk_speed)
    return (first, after, _jump(MovementTypes.JUMP_RIGHT), last, _END)


def test_a_cut_in_the_flight_before_a_near_edge_jump_finishes_that_jump() -> None:
    # The cap lands in the first flight; the walk after the landing is shorter
    # than two reads, so the next plan could not press the second jump in time.
    near = PHYSICS.walk_speed * _LEAD
    sequence = _compile(
        _chain(near), frozenset({"right"}), total_duration=0.3, since_read=_LEAD
    )

    presses = [t for t, k, e in _steps(sequence) if (k, e) == (JUMP_KEY, "keydown")]
    assert len(presses) == 2
    # Cut at the end of the second jump's flight, its key down into the landing.
    assert sequence.duration == pytest.approx(presses[1] + 0.5, abs=0.05)
    assert "right" in sequence.keys_held


def test_a_cut_far_enough_from_the_edge_jump_is_made_at_the_cap() -> None:
    far = PHYSICS.walk_speed * _LEAD * 2.5
    cut = _compile(
        _chain(far), frozenset({"right"}), total_duration=0.3, since_read=_LEAD
    )
    no_read = _compile(_chain(PHYSICS.walk_speed * _LEAD), total_duration=0.3)

    assert cut.duration == pytest.approx(0.3, abs=0.01)
    # With no read time there is nothing to judge the next plan by: as before.
    assert no_read.duration == pytest.approx(0.3, abs=0.01)
