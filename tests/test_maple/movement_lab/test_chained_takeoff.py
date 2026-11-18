"""
Chained and edge jumps, replayed: a simulated character runs a Path whose
jumps take off near a platform's open end, fed the Input Sequences
`compile_movements` makes, with the record's read latency between plans.

**What #515's record showed** (`gap-right-1`, Ellinia, 2026-11-14). The first
jump of the chain landed; the second never took off, twice:

- cycle 9 planned it from a platform's open end exactly, the one point that
  jump lands from. The edge departure's release came straight back up one
  input delay later (33 ms), and the jump key one delay after that: the
  character, still walking, was past the end by then (`TAKEOFF_STEP`);
- cycle 10, planned from the ledge it fell onto, with the walk key still down
  from the cut at the Action duration cap, read the character 22 px from that
  ledge's open end. The plan's keys went down 0.25 s after the cut and
  0.13 s after the read, and the jump key found the character in the air.

**What #521's record showed** (`gap-left-3`, after #519). Five edge take-offs
never happened:

- four times, from the rope-top ledge, the jump was planned 8 px inside the
  ledge's open end, its key went down on time, and the character walked off
  the end: the jump takes off 24 to 63 ms after its key as the compile times
  it (`TAKEOFF_LATENCY`), more than 8 px at the walk speed. The replays run
  with a key latency of 0 to 60 ms (`LATENCIES`);
- once, the walk to the jump started against the other direction key, still
  down from the Trial before: the character turned around later than the
  plan timed, and the jump key went down while it fell off a slope's end
  onto the ledge it was to take off from (`ledge_below`).

**The simulated character.** It stands on the map's platforms, in virtual px:
a direction key down accelerates it at `walk_acceleration` to the walk speed;
the key up, or the other direction key down while it still moves this way,
slows it at `walk_deceleration` (the record's turn, `gap-left-3` cycle 1:
about 1,000 px/s² across the stop and the start after it, as drag and then the
walk's force make). Past a platform's end it falls under `gravity`, at most
`fall_speed`. The jump key, on a platform, sends it up at `jump_speed` and
sideways at the walk speed the way a direction key is down (or at its speed,
with none). The jump key in the air does nothing. Every key acts `latency`
s after it is sent. Its physics are the live run's: speed 100%, the walk
Calibration constant 1.19.

**The loop around it** is the Trial's: a frame is read `AGE` s after its
capture and compiled then, with `read_at`; the next frame is captured `GAP` s
after the sequence is sent. A frame captured in the air plans nothing (the
planner places no start in the air), and the next is captured one `READ`
later. Both latencies are #515's record's, from cycle 9's cut to cycle 10's
keys.

**Its limits.** Its reads are exact and its latencies fixed; the live reads
are a few px off, and their age varies cycle to cycle. Its physics are the
ones the plans are made from, so it cannot tell whether those are the
client's: the walk, the arc and the slide are taken as the graph and the
compile take them. It has no ropes, walls, or slopes' effect on speed, and a
jump in it takes off at the walk speed even from rest, which the client's
standing jumps are not known to do. It shows each jump key now acts while the
character is on the platform its plan takes off from, and the records' ways
of failing come back without the fixes; only a live Trial checks them
(`gap-right-1`, `gap-left-3`).

**The send loop's clock.** Each Step goes out its delay plus `OVERHEAD`
after the one before it, as `KeyboardInputWrapper.duration` counts it. The
replays read `OVERHEAD` when they run, and run at several values of it
(`_at_every_overhead`), so a plan that is on time only on a quiet machine
fails here on any machine (#589).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from botting import controller
from botting.controller import InputState, KeyboardInputWrapper
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from maple.model.navigation import TAKEOFF_LEAD, Point
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
#: Seconds from a key's send to the client acting on it: none, and up to the
#: largest #521's record measured from a jump key to its take-off.
LATENCIES = [0.0, 0.03, 0.06]
_STEP = 0.0005


#: Where the replay goes: well inside the platform.
GOAL: Point = (480.0, -52.0)


@dataclass
class _Press:
    """A jump key, as the client acted on it."""

    #: The platform the character stood on then; `None` in the air.
    on: Platform | None
    #: The platform the plan's jump takes off from.
    planned: Platform | None
    #: The character's sideways speed then, virtual px/s.
    vx: float = 0.0


@dataclass
class _Character:
    """A character on the map's platforms (the module docstring says how)."""

    platforms: tuple[Platform, ...]
    x: float
    y: float
    on: Platform | None
    physics: VRPhysics
    latency: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    held: set[str] = field(default_factory=set[str])
    t: float = 0.0
    #: Each jump key press, where the client acted on it.
    presses: list[_Press] = field(default_factory=list[_Press])

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
        physics = self.physics
        way = ("right" in self.held) - ("left" in self.held)
        if way and self.vx * way >= 0:
            speed = abs(self.vx) + physics.walk_acceleration * _STEP
            self.vx = way * min(physics.walk_speed, speed)
        elif way:
            # Against its motion: the drag stops it, then the walk starts it.
            self.vx += way * physics.walk_deceleration * _STEP
        else:
            slower = abs(self.vx) - physics.walk_deceleration * _STEP
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
        self.vy = min(self.vy + self.physics.gravity * _STEP, self.physics.fall_speed)
        self.x += self.vx * _STEP
        self.y += self.vy * _STEP
        if self.vy > 0 and (landing := self._surface(self.x, top, self.y)):
            self.on = landing
            self.y = landing.y_at(self.x) or self.y
            self.vy = 0.0

    def _press(self, key: str, event: str, planned: Platform | None) -> None:
        if event == "keyup":
            self.held.discard(key)
            return
        if key == JUMP_KEY and key not in self.held:
            self.presses.append(_Press(self.on, planned, self.vx))
            if self.on is not None:
                way = ("right" in self.held) - ("left" in self.held)
                self.vx = way * self.physics.walk_speed if way else self.vx
                self.vy = -self.physics.jump_speed
                self.on = None
        self.held.add(key)

    def play(
        self,
        sequence: KeyboardInputWrapper,
        takeoff: Callable[[int], Platform | None],
    ) -> float:
        """
        Each Step at its time in the send loop, the delays before it, acted
        on `latency` later. `takeoff` names the platform the plan's component
        of that index takes off from. Returns when the last Step is sent.
        """
        at = self.t
        for keys, events, delay, origin in zip(
            sequence.keys,
            sequence.events,
            sequence.delays,
            sequence.origins,
            strict=True,
        ):
            self.run(at + self.latency)
            keys = keys if isinstance(keys, list) else [keys]
            events = events if isinstance(events, list) else [events] * len(keys)
            for key, event in zip(keys, events, strict=True):
                self._press(key, event, takeoff(origin))
            at += delay + controller.OVERHEAD
        self.run(at + self.latency)
        return at


@dataclass
class _Replay:
    arrived: bool
    #: Each jump key press, where the client acted on it.
    presses: list[_Press]
    #: How many plans were dispatched.
    plans: int

    @property
    def on_platforms(self) -> list[bool]:
        """Each press: whether the character stood on a platform."""
        return [p.on is not None for p in self.presses]

    @property
    def where_planned(self) -> list[bool]:
        """Each press: whether it found the character where its plan took off."""
        return [p.on is not None and p.on == p.planned for p in self.presses]


def _replay(
    world: WorldMap,
    start: Point,
    goal: Point,
    *,
    latency: float = 0.0,
    held: frozenset[str] = frozenset(),
    vx: float = 0.0,
    physics: VRPhysics = PHYSICS,
) -> _Replay:
    """
    The Trial's loop from `start`, on a platform, moving at `vx` with the
    direction keys `held` down (a Continuation from before).
    """
    handler = MovementHandler(corpus.LAB_HANDLE, world, corpus.LAB_IGN)
    floor = world.platform_at(start)
    assert isinstance(floor, Platform)
    y = floor.y_at(start[0])
    assert y is not None
    character = _Character(
        world.platforms, start[0], y, floor, physics, latency, vx, held=set(held)
    )
    frame, plans = 0.0, 0
    for _ in range(12):
        character.run(frame)
        read = (character.x, character.y)
        if math.dist(read, goal) <= TOLERANCE and character.on is not None:
            return _Replay(True, character.presses, plans)
        path = handler.compute_path(read, goal, physics) if character.on else None
        plan = handler.path_into_movements(path)
        if len(plan) < 2:
            frame += READ
            continue
        compile_at = frame + AGE
        character.run(compile_at)
        down = frozenset(k for k in character.held if k in ("left", "right"))
        sequence = compile_movements(
            InputState(down, next(iter(down), None), 1.0),
            movements=plan,
            handle=corpus.LAB_HANDLE,
            ign=corpus.LAB_IGN,
            speed=physics.walk_speed,
            total_duration=ACTION_DURATION,
            walk_acceleration=physics.walk_acceleration,
            walk_deceleration=physics.walk_deceleration,
            read_at=frame,
            clock=lambda at=compile_at: at,
        )
        assert sequence is not None
        plans += 1

        def takeoff(
            origin: int, plan: tuple[_MovementComponent, ...] = plan
        ) -> Platform | None:
            start = plan[origin].start if 0 <= origin < len(plan) else None
            return None if start is None else world.platform_at(start)

        frame = character.play(sequence, takeoff) + GAP
    return _Replay(False, character.presses, plans)


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(515)


@pytest.fixture(autouse=True)
def _at_every_overhead(overhead: float) -> None:
    """
    Every test here at several send-loop `OVERHEAD`s (root `conftest.overhead`),
    the replay's clock spending the same one as the compile's.

    `OVERHEAD` is measured once at import, and a loaded machine measures it
    several times larger (#589). The jump's two Steps paid it on top of its
    flight, so every key after a jump went down two `OVERHEAD`s late: from
    8 ms, the second jump key of the walking chain went down past the ledge's
    open end, and the test failed whenever the suite ran on a busy machine.
    """


@pytest.fixture(scope="module")
def world() -> WorldMap:
    """The record's chain, on a synthetic map (`fixture_maps.ledge_chain`)."""
    return WorldMap.from_map_data(fixture_maps.ledge_chain())


# --- the chain, replayed -------------------------------------------------------------

#: Starts on the floor, 20 px apart: wherever the Action duration cap lands in
#: the chain.
STARTS = [float(x) for x in range(20, 200, 20)]


@pytest.mark.parametrize("walking", [False, True], ids=["standing", "walking"])
@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("start_x", STARTS)
def test_every_jump_key_of_the_chain_goes_down_on_a_platform(
    world: WorldMap, start_x: float, latency: float, walking: bool
) -> None:
    # Standing, the walk's acceleration makes each take-off a few px early;
    # walking already, `right` down from before, as `gap-left-3`'s chain
    # started, it takes off where the compile times it, then the latency on.
    replay = _replay(
        world,
        (start_x, 0.0),
        GOAL,
        latency=latency,
        held=frozenset({"right"}) if walking else frozenset(),
        vx=PHYSICS.walk_speed if walking else 0.0,
    )

    assert replay.arrived
    # Both jumps, each from the platform its plan takes off from.
    assert replay.where_planned == [True, True]


def test_the_path_takes_off_inside_both_open_ends(world: WorldMap) -> None:
    handler = MovementHandler(corpus.LAB_HANDLE, world, corpus.LAB_IGN)
    path = handler.compute_path((40.0, 0.0), GOAL, PHYSICS)

    assert path is not None
    jumps = [m for m in path.moves if m.kind.name == "JUMP"]
    assert len(jumps) == 2
    margin = PHYSICS.walk_speed * TAKEOFF_LEAD
    for jump in jumps:
        assert isinstance(jump.start_on, Platform)
        assert jump.start_on.right - jump.start[0] >= margin - 1e-6


# --- a walk to an edge jump that starts against the other key (#521) ---------------

#: Where the left-going replays go: on the platform above the ledge's far end.
LEFT_GOAL: Point = (-200.0, -55.0)


@pytest.fixture(scope="module")
def below() -> WorldMap:
    """`gap-left-3`'s first jump, on a synthetic map (`fixture_maps.ledge_below`)."""
    return WorldMap.from_map_data(fixture_maps.ledge_below())


@pytest.mark.parametrize("latency", [0.0, 0.06])
@pytest.mark.parametrize("start_x", [60.0, 100.0, 140.0])
def test_a_walk_into_an_edge_jump_against_the_other_key_takes_off_where_planned(
    below: WorldMap, start_x: float, latency: float
) -> None:
    # Walking right at full speed, `right` still down from before; the Path
    # goes left: off the platform's end onto the ledge, along it, and up off
    # its open end onto the platform above.
    replay = _replay(
        below,
        (start_x, -45.0),
        LEFT_GOAL,
        latency=latency,
        held=frozenset({"right"}),
        vx=PHYSICS.walk_speed,
    )

    assert replay.arrived
    assert replay.presses
    assert all(replay.where_planned)


# --- the five take-offs of `gap-left-3`, on Ellinia (#521) -----------------------------

#: The jump batch's physics (the record's header).
JUMP_BATCH = Calibration(walk=1.19, jump=0.96, climb=0.95)

#: Each failed take-off's cycle: its read, and the direction key down then,
#: the character walking that way at the walk speed.
GAP_LEFT_3 = {
    "cycle 1": ((-396.3, -57.6), "right"),
    "cycle 11": ((-337.4, -2.5), "left"),
    "cycle 17": ((-334.9, -2.7), "left"),
    "cycle 22": ((-318.5, -1.6), "left"),
    "cycle 29": ((-319.9, -2.1), "left"),
}


@pytest.mark.client_files
@pytest.mark.parametrize("latency", LATENCIES)
@pytest.mark.parametrize("cycle", list(GAP_LEFT_3))
def test_gap_left_3s_take_offs_happen_where_planned(cycle: str, latency: float) -> None:
    world = WorldMap.load("Victoria Road: Ellinia")
    physics = VRPhysics.load(calibration=JUMP_BATCH)
    start, key = GAP_LEFT_3[cycle]
    way = 1 if key == "right" else -1

    replay = _replay(
        world,
        start,
        (-620.0, -52.0),
        latency=latency,
        held=frozenset({key}),
        vx=way * physics.walk_speed,
        physics=physics,
    )

    assert replay.arrived
    assert replay.presses
    assert all(replay.where_planned)


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
        at += delay + controller.OVERHEAD
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
    assert _press_time(sequence) == pytest.approx(walk, abs=controller.OVERHEAD * 2)
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
