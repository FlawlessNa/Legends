"""
`FootholdGraph` on synthetic fixtures, each with its moves written out by hand.

The fixture physics keeps the arithmetic by hand: a jump rises 80 px in 0.4 s
and comes back down to its take-off's height 0.8 s after leaving it, the walk
is 101 px/s (so a level jump carries 80.8 px, never a whole px), and the fall
speed is never reached. So:

- a jump that lands `d` px below its take-off takes `0.4 + sqrt((80 + d) / 500)` s;
- a fall from rest of `d` px takes `sqrt(d / 500)` s.

A fixture lists every move the graph should hold, as `(kind, direction, from,
low, high, to)`, ranges in whole px. A fixture that pins the arc's own ranges
builds with `traced`, which keeps the landings `JUMP_RISE_SHARE` and
`LANDING_MARGIN` leave out (#509), and the take-offs `TAKEOFF_STEP` leaves out
(#515); each is tested on its own.
"""

import math
from dataclasses import replace

import numpy as np
import pytest

from game_data.catalogue import Foothold, Rope
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import (
    LANDING_MARGIN,
    PORTAL_TIME,
    ROPE_GRAB_REACH,
    TAKEOFF_STEP,
    TELEPORT_TIME,
    Direction,
    FootholdGraph,
    MoveKind,
    Path,
    Terrain,
)
from maple.model.world import Platform

PHYSICS = VRPhysics(
    walk_speed=101.0,
    jump_speed=400.0,
    gravity=1000.0,
    fall_speed=1e6,
    climb_speed=50.0,
    teleport_reach=150.0,
)

J, D, F, W, C = (
    MoveKind.JUMP,
    MoveKind.DROP,
    MoveKind.FALL,
    MoveKind.WALK,
    MoveKind.CLIMB,
)
L, R, U, DN = Direction.LEFT, Direction.RIGHT, Direction.UP, Direction.DOWN


def platform(fh_id: int, left: int, right: int, y: int) -> Platform:
    return Platform(0, (Foothold("map", 0, 1, fh_id, left, y, right, y, 0, 0),))


def wall(fh_id: int, x: int, top: int, bottom: int) -> Foothold:
    return Foothold("map", 0, 1, fh_id, x, top, x, bottom, 0, 0)


def rope(rope_id: int, x: int, top: int, bottom: int, *, uf: bool = True) -> Rope:
    return Rope("map", rope_id, x, top, bottom, False, uf, 0)


def traced(
    platforms: list[Platform], walls: list[Foothold] | None = None
) -> FootholdGraph:
    """
    The graph with every landing and take-off the arc traces, however near
    the top of the arc or a platform's end: the fixtures that pin the arc
    itself.
    """
    return FootholdGraph.from_surfaces(
        platforms,
        walls or [],
        [],
        PHYSICS,
        rise_share=1.0,
        landing_margin=0.0,
        takeoff_step=0.0,
    )


def landing_time(drop: float) -> float:
    return 0.4 + math.sqrt((80 + drop) / 500)


def fall_time(drop: float) -> float:
    return math.sqrt(drop / 500)


type Summary = set[tuple[MoveKind, Direction | None, str, int, int, str]]


def summary(graph: FootholdGraph, names: dict[Platform | Rope, str]) -> Summary:
    return {
        (
            m.kind,
            m.direction,
            names[m.source],
            round(m.low),
            round(m.high),
            names[m.target],
        )
        for m in graph.moves
    }


def contiguous(path: Path) -> bool:
    return all(
        a.end == b.start for a, b in zip(path.moves, path.moves[1:], strict=False)
    )


# --- a walk ------------------------------------------------------------------


def test_a_lone_platform_holds_no_moves_and_a_path_along_it_is_one_walk() -> None:
    a = platform(1, 0, 100, 0)
    graph = FootholdGraph.from_surfaces([a], [], [], PHYSICS)

    assert graph.moves == ()
    path = graph.path((10, 0), (90, 0))
    assert path is not None
    assert [(m.kind, m.direction, m.start, m.end) for m in path.moves] == [
        (W, R, (10, 0), (90, 0))
    ]
    assert path.duration == pytest.approx(80 / 101)


def test_a_path_from_a_point_to_itself_has_no_moves() -> None:
    graph = FootholdGraph.from_surfaces([platform(1, 0, 100, 0)], [], [], PHYSICS)

    assert graph.path((50, 0), (50, 0)) == Path(())


# --- a gap jump ----------------------------------------------------------------


def gap() -> tuple[Platform, Platform]:
    return platform(1, 0, 100, 0), platform(2, 156, 300, 0)


def test_a_gap_is_jumped_both_ways_from_the_stretches_that_clear_it() -> None:
    a, b = gap()
    graph = traced([a, b])

    # x + 80.8 >= 156 from A; x - 80.8 <= 100 from B. Nothing lies below.
    assert summary(graph, {a: "A", b: "B"}) == {
        (J, R, "A", 76, 100, "B"),
        (J, L, "B", 156, 180, "A"),
    }
    right = next(m for m in graph.moves if m.direction is R)
    assert right.landing_low == pytest.approx((156.8, 0))
    assert right.landing_high == pytest.approx((180.8, 0))
    assert right.duration_low == pytest.approx(0.8)


def test_a_path_across_a_gap_jumps_it_and_walks_the_rest() -> None:
    a, b = gap()
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS)

    path = graph.path((10, 0), (250, 0))

    assert path is not None
    assert [m.kind for m in path.moves] == [W, J, W]
    assert contiguous(path)
    assert path.moves[0].start == (10, 0)
    assert path.moves[-1].end == (250, 0)
    assert path.duration == pytest.approx(240 / 101)


def test_a_start_inside_a_jumps_stretch_takes_off_right_there() -> None:
    a, b = gap()
    graph = traced([a, b])

    path = graph.path((90.5, 0), (171.3, 0))

    assert path is not None
    assert [(m.kind, m.start) for m in path.moves] == [(J, (90.5, 0))]
    assert path.moves[0].end == pytest.approx((171.3, 0))


# --- a drop, and a one-way drop ------------------------------------------------


def test_a_drop_onto_a_platform_within_a_jump_can_be_jumped_back_up() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, -1000, 1000, 60)
    graph = traced([a, b])

    # From B, a jump up (top at -20) lands on A above it; a jump sideways
    # passes A on the way up and lands on it on the way down, 0.6 s and
    # 60.6 px later, from B's x in [-60.6, 39.4] going right.
    assert summary(graph, {a: "A", b: "B"}) == {
        (D, DN, "A", 0, 100, "B"),
        (F, L, "A", 0, 0, "B"),
        (F, R, "A", 100, 100, "B"),
        (J, L, "A", 0, 80, "B"),
        (J, R, "A", 20, 100, "B"),
        (J, U, "B", 0, 100, "A"),
        (J, R, "B", -60, 39, "A"),
        (J, L, "B", 61, 160, "A"),
    }
    by = {(m.kind, m.direction, m.low): m for m in graph.moves}
    assert by[D, DN, 0].duration_low == pytest.approx(fall_time(60))
    assert by[F, L, 0].landing_low == pytest.approx((-101 * fall_time(60), 60))
    assert by[J, L, 0].landing_low == pytest.approx((-101 * landing_time(60), 60))
    assert by[J, U, 0].duration_low == pytest.approx(landing_time(-60))


def test_a_drop_too_far_to_jump_back_is_one_way() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, -1000, 1000, 200)
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS)

    assert summary(graph, {a: "A", b: "B"}) == {
        (D, DN, "A", 0, 100, "B"),
        (F, L, "A", 0, 0, "B"),
        (F, R, "A", 100, 100, "B"),
        # A sideways jump takes off `TAKEOFF_STEP` of walking (3.3 px) inside
        # the open end it heads for.
        (J, L, "A", 4, 80, "B"),
        (J, R, "A", 20, 96, "B"),
    }
    assert graph.path((50, 200), (50, 0)) is None
    path = graph.path((50, 0), (50, 200))
    assert path is not None
    assert [m.kind for m in path.moves] == [D]


def test_a_drop_lands_on_the_first_platform_below_within_reach() -> None:
    a = platform(1, 0, 100, 0)
    middle = platform(2, 50, 100, 300)
    far = platform(3, -1000, 1000, 600)
    graph = FootholdGraph.from_surfaces([a, middle, far], [], [], PHYSICS)

    drops = {
        (round(m.low), round(m.high), m.target)
        for m in graph.moves
        if m.kind is D and m.source == a
    }
    # 600 px is beyond `DROP_REACH`; the middle platform catches 50..100.
    assert drops == {(50, 100, middle)}


# --- a wall that blocks a jump ------------------------------------------------


def test_a_wall_in_a_gap_blocks_the_jumps_that_meet_it_below_its_top() -> None:
    a, b = gap()
    graph = traced([a, b], [wall(9, 150, -60, 0)])

    # The arc is above -60 between 0.2 s and 0.6 s after take-off: it clears
    # x = 150 from A's x > 89.4, and from B's x > 170.2.
    assert summary(graph, {a: "A", b: "B"}) == {
        (J, R, "A", 90, 100, "B"),
        (J, L, "B", 171, 180, "A"),
    }


def test_a_wall_rising_from_an_end_closes_it_and_a_cliff_below_one_does_not() -> None:
    a, ground = platform(1, 0, 100, 0), platform(2, -1000, 1000, 300)
    walls = [wall(8, 100, -100, 0), wall(9, 0, 0, 300)]
    graph = FootholdGraph.from_surfaces([a, ground], walls, [], PHYSICS)

    falls = {m.direction for m in graph.moves if m.kind is F}
    jumps_from_right_end = [
        m for m in graph.moves if m.kind is J and m.direction is R and m.high == 100
    ]
    assert falls == {L}
    assert jumps_from_right_end == []


# --- a rope ------------------------------------------------------------------


def test_a_rope_is_grabbed_climbed_and_left_by_the_expected_moves() -> None:
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 0, -202)
    r = rope(1, 0, -200, -40)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    names: dict[Platform | Rope, str] = {ground: "G", top: "T", r: "R"}
    # From G, a sideways jump crosses x = 0 inside the rope's height between
    # 0.117 s and 0.683 s after take-off, so from |x| in [11.8, 69.0]. From T,
    # a drop within `ROPE_GRAB_REACH` (11.6) of the rope's top grabs the rope.
    assert summary(graph, names) == {
        (J, L, "G", 12, 68, "R"),
        (J, R, "G", -68, -12, "R"),
        (J, U, "G", 0, 0, "R"),
        (D, DN, "T", -300, -12, "G"),
        (F, L, "T", -300, -300, "G"),
        (F, R, "T", 0, 0, "G"),
        (J, L, "T", -296, -220, "G"),
        (J, R, "T", -80, -4, "G"),
        (C, DN, "T", 0, 0, "R"),
        (C, U, "R", -200, -200, "T"),
        (F, DN, "R", -40, -40, "G"),
        (J, L, "R", -200, -40, "G"),
        (J, R, "R", -200, -40, "G"),
    }
    up = next(m for m in graph.moves if m.kind is J and m.direction is U)
    assert up.landing_low == (0, -40)


def test_a_path_up_a_rope_jumps_to_it_climbs_it_and_steps_off_at_the_top() -> None:
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 0, -202)
    r = rope(1, 0, -200, -40)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    path = graph.path((0, 0), (-100, -202))

    assert path is not None
    assert [(m.kind, m.direction) for m in path.moves] == [
        (J, U),
        (C, U),
        (C, U),
        (W, L),
    ]
    assert contiguous(path)
    assert path.moves[0].end_on == r
    assert path.moves[-1].end == (-100, -202)


def test_a_rope_whose_top_is_not_usable_has_no_step_at_the_top() -> None:
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 0, -202)
    r = rope(1, 0, -200, -40, uf=False)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    assert not [m for m in graph.moves if m.kind is C]


def test_no_drop_takes_off_within_grab_reach_of_a_ropes_top() -> None:
    # The down key grabs a rope from the platform at its top (#516): a drop
    # planned there climbs down the rope instead. Both sides of the rope.
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 300, -202)
    r = rope(1, 0, -200, -40)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    drops = sorted((round(m.low), round(m.high)) for m in graph.moves if m.kind is D)
    assert ROPE_GRAB_REACH == pytest.approx(11.6)
    assert drops == [(-300, -12), (12, 300)]


def test_a_drop_beside_a_rope_whose_top_is_not_usable_is_kept() -> None:
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 300, -202)
    r = rope(1, 0, -200, -40, uf=False)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    drops = [(round(m.low), round(m.high)) for m in graph.moves if m.kind is D]
    assert drops == [(-300, 300)]


def test_a_path_down_from_a_ropes_top_climbs_down_or_leaves_the_reach_first() -> None:
    # From 9 px off the rope's x, as the live record's coarse read was: the
    # Path to the ground starts no drop within reach of the rope.
    ground = platform(1, -500, 500, 0)
    top = platform(2, -300, 300, -202)
    r = rope(1, 0, -200, -40)
    graph = FootholdGraph.from_surfaces([ground, top], [], [r], PHYSICS)

    path = graph.path((-9, -202), (-9, 0))

    assert path is not None
    assert contiguous(path)
    drops = [m for m in path.moves if m.kind is D]
    assert all(abs(m.start[0]) > ROPE_GRAB_REACH for m in drops)


def test_a_platform_crossing_a_rope_is_stepped_on_and_off_mid_rope() -> None:
    ledge = platform(1, -50, 50, -100)
    r = rope(1, 0, -200, -40)
    graph = FootholdGraph.from_surfaces([ledge], [], [r], PHYSICS)

    climbs = {
        (m.direction, m.source == ledge, m.landing_low)
        for m in graph.moves
        if m.kind is C
    }
    assert climbs == {(U, True, (0, -100)), (DN, False, (0, -100))}


# --- joins, portals and teleports --------------------------------------------


def test_a_platform_ending_on_another_walks_across_and_does_not_fall() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, 100, 200, 0)
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS)

    walks = {(m.direction, m.source, m.target) for m in graph.moves if m.kind is W}
    assert walks == {(R, a, b), (L, b, a)}
    assert not [m for m in graph.moves if m.kind is F]
    path = graph.path((10, 0), (190, 0))
    assert path is not None
    assert contiguous(path)
    assert path.moves[-1].end == (190, 0)
    assert path.duration == pytest.approx(180 / 101)
    # A jump across the join costs the same, and the tie goes to the walk. The
    # jump ranges stay stored.
    assert {m.kind for m in path.moves} == {W}
    assert [m for m in graph.moves if m.kind is J and m.target is b]


def test_a_portal_takes_the_path_to_its_target() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, 5000, 5100, -3000)
    graph = FootholdGraph.from_surfaces(
        [a, b], [], [], PHYSICS, portals=[((50, -4), (5050, -3003))]
    )

    portals = [m for m in graph.moves if m.kind is MoveKind.PORTAL]
    assert [(m.source, m.low, m.target, m.landing_low) for m in portals] == [
        (a, 50, b, (5050, -3000))
    ]
    path = graph.path((0, 0), (5100, -3000))
    assert path is not None
    assert [m.kind for m in path.moves] == [W, MoveKind.PORTAL, W]
    assert path.duration == pytest.approx(100 / 101 + PORTAL_TIME)
    assert graph.path((5100, -3000), (0, 0)) is None


def test_teleports_are_added_only_for_a_character_that_has_the_skill() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, 200, 400, -50)

    without = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS)
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS, teleport=True)

    assert not [m for m in without.moves if m.kind is MoveKind.TELEPORT]
    right = [
        (m.source, round(m.low), round(m.high), m.target, m.duration_low)
        for m in graph.moves
        if m.kind is MoveKind.TELEPORT and m.direction is R
    ]
    # x + 150 lands on B, 50 px above, within half the reach.
    assert right == [(a, 50, 100, b, TELEPORT_TIME)]


# --- placing points ----------------------------------------------------------


def test_a_start_on_no_surface_is_refused() -> None:
    graph = FootholdGraph.from_surfaces([platform(1, 0, 100, 0)], [], [], PHYSICS)

    with pytest.raises(ValueError, match="start"):
        graph.path((50, -100), (60, 0))
    with pytest.raises(ValueError, match="goal"):
        graph.path((50, 0), (500, 0))


def test_a_point_near_a_surface_is_placed_on_it() -> None:
    graph = FootholdGraph.from_surfaces([platform(1, 0, 100, 0)], [], [], PHYSICS)

    path = graph.path((10, -6), (90, 5))

    assert path is not None
    assert path.moves[0].start == (10, 0)
    assert path.moves[-1].end == (90, 0)


def test_reachable_lists_the_surfaces_a_path_reaches() -> None:
    a, b = platform(1, 0, 100, 0), platform(2, -1000, 1000, 200)
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS)

    assert graph.reachable((50, 0)) == (a, b)
    assert graph.reachable((50, 200)) == (b,)


# --- the arc -----------------------------------------------------------------


def test_a_long_jump_lands_when_the_physics_says_past_the_fall_speed() -> None:
    physics = VRPhysics(125.0, 555.0, 2000.0, 670.0, 125.0, 150.0)
    terrain = Terrain([platform(1, -5000, 5000, 1000)], [], [], physics)

    hits = terrain.sweep(np.array([0.0]), np.array([0.0]), 125.0, -555.0)

    t = physics.jump_landing_time(1000)
    assert hits.surface.tolist() == [0]
    assert hits.t[0] == pytest.approx(t)
    assert (hits.x[0], hits.y[0]) == pytest.approx((125 * t, 1000))


# --- landings only an exact take-off makes (#509) -------------------------------


def test_a_platform_too_near_the_top_of_the_jump_is_not_jumped_onto() -> None:
    # The arc tops out 80 px up; 0.95 of it is 76. Live, 40 jumps planned to
    # land at the top of the arc, and none landed there.
    ground = platform(1, 0, 200, 0)
    near_top, within = platform(2, 150, 400, -78), platform(3, 150, 400, -76)

    too_high = FootholdGraph.from_surfaces([ground, near_top], [], [], PHYSICS)
    reached = FootholdGraph.from_surfaces([ground, within], [], [], PHYSICS)

    def up(graph: FootholdGraph) -> set[tuple[Direction | None, Platform | Rope]]:
        return {
            (m.direction, m.target)
            for m in graph.moves
            if m.kind is J and m.source == ground
        }

    assert up(too_high) == set()
    assert too_high.path((50, 0), (300, -78)) is None
    assert up(reached) == {(R, within), (U, within)}
    assert reached.path((50, 0), (300, -76)) is not None


def test_a_sideways_jump_lands_a_margin_inside_an_open_end_of_its_platform() -> None:
    a, b = gap()
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS, takeoff_step=0.0)

    # As traced, A's x in [76, 100] lands B's x in [156.8, 180.8]. A landing
    # 15.5 px inside B's left end (171.5) needs a take-off from x >= 90.7;
    # back, B's x - 80.8 <= 84.5 needs x <= 165.3.
    assert summary(graph, {a: "A", b: "B"}) == {
        (J, R, "A", 91, 100, "B"),
        (J, L, "B", 156, 165, "A"),
    }
    path = graph.path((10, 0), (250, 0))
    assert path is not None
    jump = next(m for m in path.moves if m.kind is J)
    assert jump.end[0] >= 156 + LANDING_MARGIN


def test_an_end_another_platform_continues_needs_no_margin() -> None:
    # B's left end is open; its right end joins C, so a landing there walks on.
    a = platform(1, 0, 100, 0)
    b, c = platform(2, 156, 200, 0), platform(3, 200, 400, 0)
    graph = FootholdGraph.from_surfaces([a, b, c], [], [], PHYSICS)

    from_c = [m for m in graph.moves if (m.kind, m.direction, m.source) == (J, L, c)]
    # C's x - 80.8 lands on B from x 236.8; 15.5 inside B's open left end
    # needs x >= 252.3. Up to C's x 280 it lands 0.8 px short of the join.
    assert [(round(m.low), round(m.high), m.target) for m in from_c] == [(253, 280, b)]


# --- take-offs only an exact walk makes (#515) ------------------------------------


def test_a_sideways_jump_takes_off_a_step_of_walking_inside_the_end_it_heads_for() -> (
    None
):
    a, b = gap()
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS, landing_margin=0.0)

    # As traced, A's x in [76, 100] lands on B, and B's x in [156, 180] on A.
    # One Step of walking at 101 px/s is 3.3 px: A's take-offs end at 96.7 and
    # B's start at 159.3, each short of the open end it heads for.
    assert summary(graph, {a: "A", b: "B"}) == {
        (J, R, "A", 76, 96, "B"),
        (J, L, "B", 160, 180, "A"),
    }
    path = graph.path((10, 0), (250, 0))
    assert path is not None
    jump = next(m for m in path.moves if m.kind is J)
    assert a.right - jump.start[0] >= PHYSICS.walk_speed * TAKEOFF_STEP


def test_a_jump_only_the_open_end_itself_takes_off_for_is_no_move() -> None:
    # A level jump carries 80.8 px: only A's x 100, its open end, reaches B at
    # 180, and back only B's x 180, its own open end. Live, a jump planned so
    # took off after the character had walked off that end (#515).
    a, b = platform(1, 0, 100, 0), platform(2, 180, 300, 0)
    names: dict[Platform | Rope, str] = {a: "A", b: "B"}

    exact = FootholdGraph.from_surfaces(
        [a, b], [], [], PHYSICS, landing_margin=0.0, takeoff_step=0.0
    )
    graph = FootholdGraph.from_surfaces([a, b], [], [], PHYSICS, landing_margin=0.0)

    assert summary(exact, names) == {
        (J, R, "A", 100, 100, "B"),
        (J, L, "B", 180, 180, "A"),
    }
    assert summary(graph, names) == set()
    assert graph.path((50, 0), (250, 0)) is None


def test_the_take_off_margin_is_a_step_of_the_characters_own_walk() -> None:
    # Twice the walk speed: a level jump carries 161.6 px, so all of A lands on
    # B as traced, and one Step of walking is 6.7 px.
    a, b = gap()
    faster = replace(PHYSICS, walk_speed=2 * PHYSICS.walk_speed)
    graph = FootholdGraph.from_surfaces([a, b], [], [], faster, landing_margin=0.0)

    right = [m for m in graph.moves if (m.kind, m.direction, m.source) == (J, R, a)]
    assert [(round(m.low), round(m.high)) for m in right] == [(0, 93)]
