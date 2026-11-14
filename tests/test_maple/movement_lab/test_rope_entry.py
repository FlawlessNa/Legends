"""
Onto a ladder from above with coarse reads (#516), replayed: a simulated
character on Ellinia's ladder at x 627, its position read as the minimap
alone reads it, the middle of the 16 px canvas pixel its feet are in, fed the
Input Sequences `compile_movements` makes from the Paths `MovementHandler`
plans.

**What the record showed** (`physics-ladder-only`, 2026-11-14). Every read at
the top of Ellinia was coarse (#517), so x read 618, 634 or 650 only. The
Trials' waypoint at the ladder's top, (627, -759), is a point on the platform:
each cycle planned one walk of 7 or 9 px towards it, and each walk carried the
character to the read's other side. 116 walks in `ladder-up-2`, 248 cycles in
`ladder-mid-2`, and no end. A Path that went *down* the ladder entered it
every time it was planned: the down key grabs it from within reach.

**The map.** Ellinia's own numbers: the platform at y -759 from 557 to 946,
the ladder at x 627 from its top at -757 down to -465, and its minimap
transform (centre (1214, 4547), `mag` 4), so the reads land on the record's
618 and 634. Nothing below the ladder, so no drop or fall takes the Path off
it.

**The simulated character.** On the platform, as `test_walk_overshoot`'s: a
direction key down accelerates it to its top speed, the key up slides it to a
stop, at the record's calibrated walk (1.19). The down key held within
`ROPE_GRAB_REACH` of the ladder's x grabs it; down on the ladder climbs down
at the climb speed. A cycle reads the position, plans, compiles, plays the
sequence, and reads again `GAP` later.

**Its limits.** The reads are the minimap's, exact to their canvas pixel; the
live ones are a few px off and some are fused. There is no read age (#503's
lead is not replayed), and the grab reach is the planner's own lower bound, so
the replay cannot say what the client's reach is: it shows the loop stops
walking at the top, and enters the ladder from either side, given these. Only
a live Trial checks it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from itertools import pairwise

import pytest

from botting.controller import InputState, KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD
from game_data.catalogue import Minimap
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    compile_movements,
)
from maple.model.mechanics.physics import Calibration, VRPhysics
from maple.model.navigation import ROPE_GRAB_REACH
from maple.model.world import WorldMap
from maple.screen.position import feet_of_marker, marker_of_feet
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.fixture_maps import _footholds, _map, _rope

LADDER_X = 627.0
LADDER_TOP = -757.0
LADDER_BOTTOM = -465.0
PLATFORM_Y = -759.0
#: The Trials' waypoint at the ladder's top: a point on the platform.
TOP = (627.0, -759.0)
#: A point down the ladder.
DOWN = (627.0, -600.0)
#: The physics the live run planned with: the client's, walk calibrated 1.19.
PHYSICS = VRPhysics.from_game_files(
    corpus.LAB_PHYSICS_VALUES, calibration=Calibration(walk=1.19)
)
#: Seconds from a sequence's end, or a cycle that sent nothing, to the next read.
GAP = 0.12
#: The Action duration cap the Trials ran with (`TrialRunner`).
ACTION_DURATION = 1.0
_STEP = 0.0005


def _world() -> WorldMap:
    data = _map(
        900_516_001,
        "ellinia_ladder_top",
        _footholds((557, -759, 946, -759)),
        (_rope(1, 627, -757, -465, ladder=True),),
    )
    ellinia = Minimap(center_x=1214, center_y=4547, mag=4, width=3000, height=2000)
    return WorldMap.from_map_data(replace(data, minimap=ellinia))


WORLD = _world()
assert WORLD.minimap is not None
TRANSFORM = WORLD.minimap
#: Half a canvas px: how far off a coarse read's x may be.
HALF_PIXEL = TRANSFORM.scale / 2


@dataclass
class _Character:
    """On the platform, or on the ladder once the down key grabs it."""

    x: float
    y: float = PLATFORM_Y
    v: float = 0.0
    held: set[str] = field(default_factory=set[str])
    on_ladder: bool = False
    t: float = 0.0

    def run(self, until: float) -> None:
        while self.t < until:
            self.t += _STEP
            if self.on_ladder:
                if "down" in self.held:
                    self.y = min(LADDER_BOTTOM, self.y + PHYSICS.climb_speed * _STEP)
                continue
            if "down" in self.held and abs(self.x - LADDER_X) <= ROPE_GRAB_REACH:
                self.on_ladder, self.x, self.y, self.v = True, LADDER_X, LADDER_TOP, 0.0
                continue
            way = ("right" in self.held) - ("left" in self.held)
            if way and self.v * way >= 0:
                speed = min(
                    PHYSICS.walk_speed, abs(self.v) + PHYSICS.walk_acceleration * _STEP
                )
                self.v = way * speed
            elif way:
                self.v += (
                    way
                    * (PHYSICS.walk_acceleration + PHYSICS.walk_deceleration)
                    * _STEP
                )
            else:
                slowed = max(0.0, abs(self.v) - PHYSICS.walk_deceleration * _STEP)
                self.v = math.copysign(slowed, self.v)
            self.x += self.v * _STEP

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

    def coarse_read(self) -> tuple[float, float]:
        """The minimap's read: the middle of the canvas pixel the feet are in."""
        return feet_of_marker(TRANSFORM, marker_of_feet(TRANSFORM, (self.x, self.y)))


@dataclass
class _Replay:
    character: _Character
    #: Each cycle's Movement Plan, sentinel left out; empty when nothing was sent.
    plans: list[list[MovementTypes]] = field(default_factory=list)

    @property
    def walks(self) -> list[MovementTypes]:
        """The way each Plan that was only a walk walked."""
        return [p[0] for p in self.plans if len(p) == 1 and _is_walk(p[0])]

    @property
    def turns(self) -> int:
        """How many times a walk-only Plan walked the other way from the last."""
        walks = self.walks
        return sum(a is not b for a, b in pairwise(walks))


def _is_walk(kind: MovementTypes) -> bool:
    return kind in (MovementTypes.WALK_LEFT, MovementTypes.WALK_RIGHT)


@pytest.fixture(autouse=True)
def _seeded() -> None:
    """The Steps' delays are drawn at random: the same draws every run."""
    random.seed(516)


def _replay(
    start: float, goal: tuple[float, float], *, fixed: bool, cycles: int = 30
) -> _Replay:
    """
    The loop from `start` to `goal`, on coarse reads only.

    `fixed`: plan as `MovementsMixin` now does, with the coarse read's own
    resolution; otherwise as the live run did, from the read taken as exact.
    """
    handler = MovementHandler(corpus.LAB_HANDLE, WORLD, corpus.LAB_IGN)
    character = _Character(start)
    replay = _Replay(character)
    for _ in range(cycles):
        if character.on_ladder:
            break
        path = handler.compute_path(
            character.coarse_read(),
            goal,
            PHYSICS,
            resolution=HALF_PIXEL if fixed else 0.0,
        )
        plan = handler.path_into_movements(path)
        replay.plans.append([c.movement_type for c in plan[:-1]])
        if len(plan) > 1:
            held = frozenset(k for k in character.held if k in ("left", "right"))
            sequence = compile_movements(
                InputState(held, next(iter(held), None), 1.0),
                movements=plan,
                handle=corpus.LAB_HANDLE,
                ign=corpus.LAB_IGN,
                speed=PHYSICS.walk_speed,
                climb_speed=PHYSICS.climb_speed,
                total_duration=ACTION_DURATION,
                walk_acceleration=PHYSICS.walk_acceleration,
                walk_deceleration=PHYSICS.walk_deceleration,
            )
            assert sequence is not None
            character.play(sequence)
        character.run(character.t + GAP)
    return replay


#: Where the character may stand when the loop reaches the ladder's top: every
#: 2 px across the canvas pixels either side of the ladder's x and its own.
NEAR = [float(x) for x in range(602, 652, 2)]


# --- the record, reproduced --------------------------------------------------------


def test_the_replay_reads_the_records_two_values_either_side_of_the_ladder() -> None:
    assert _Character(620.0).coarse_read() == (618.0, -763.0)
    assert _Character(630.0).coarse_read() == (634.0, -763.0)


@pytest.mark.parametrize("start", NEAR)
def test_the_replay_walks_either_side_of_the_ladder_as_the_record_did(
    start: float,
) -> None:
    replay = _replay(start, TOP, fixed=False)

    # One walk a cycle, back and forth, with no end.
    assert len(replay.walks) == len(replay.plans) == 30
    assert replay.turns >= 5


# --- the fix -----------------------------------------------------------------------


@pytest.mark.parametrize("start", NEAR)
def test_the_loop_stops_walking_once_the_read_holds_the_ladders_top(
    start: float,
) -> None:
    replay = _replay(start, TOP, fixed=True)

    # At most one walk the other way, then nothing: the character stands in
    # the canvas pixel that holds the goal, as near as the read can tell. (Up
    # to 15 px off the ladder: a Path down it walks the rest, below.)
    assert replay.turns <= 1
    assert len(replay.walks) <= 3
    assert all(not plan for plan in replay.plans[-20:])
    assert replay.character.coarse_read() == _Character(TOP[0]).coarse_read()


@pytest.mark.parametrize("fixed", [False, True], ids=["as-run", "fixed"])
@pytest.mark.parametrize("start", [570.0, *NEAR, 700.0, 760.0])
def test_a_path_down_the_ladder_enters_it_from_either_side(
    start: float, fixed: bool
) -> None:
    # Before #516 too: the walk holds down from its first Step, and its
    # direction stays down through the climb, so wherever the coarse read put
    # its end, the character grabs the ladder on coming within reach.
    replay = _replay(start, DOWN, fixed=fixed, cycles=6)

    assert replay.character.on_ladder
    for plan in replay.plans:
        # Walks one way (a long one cut into pieces), then down the ladder.
        first = plan.index(MovementTypes.CLIMB_DOWN)
        assert len(set(plan[:first])) <= 1
        assert all(_is_walk(kind) for kind in plan[:first])
        assert set(plan[first:]) == {MovementTypes.CLIMB_DOWN}
