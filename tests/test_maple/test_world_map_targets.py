"""
What the decision makers ask a `WorldMap` (#398): a random point on its
platforms, the platform or the rope at a point, and its NPCs. On the movement
lab's Fixture maps, built by hand: no game data store.
"""

import random
from collections import Counter
from dataclasses import replace

import pytest

from game_data.catalogue import Spawn
from maple.model.world import SURFACE_TOLERANCE, WorldMap
from tests.test_maple.movement_lab.fixture_maps import (
    jump_gap,
    jump_ledge,
    rope_grab,
    walk_corridor,
)

#: Three platforms in a row, each 200 px wide: 0-200, 250-450 and 500-700.
GAP = WorldMap.from_map_data(jump_gap())
#: A floor 0-600 at y 0, and a shelf 200-400 at y -50.
LEDGE = WorldMap.from_map_data(jump_ledge())


def test_a_random_point_lies_on_a_platform() -> None:
    rng = random.Random(1)
    corridor = WorldMap.from_map_data(walk_corridor())

    for _ in range(200):
        x, y = corridor.random_point(rng=rng)
        platform = corridor.platforms[0]
        assert platform.left <= x <= platform.right
        assert platform.y_at(x) == y


def test_platforms_are_drawn_by_their_width() -> None:
    """The floor is three times as wide as the shelf: it is drawn three times as often."""
    rng = random.Random(2)

    drawn = Counter(LEDGE.platform_at(LEDGE.random_point(rng=rng)) for _ in range(4000))

    floor, shelf = LEDGE.platforms
    assert drawn[floor] / drawn[shelf] == pytest.approx(3.0, rel=0.1)


def test_a_point_is_drawn_among_the_platforms_given_only() -> None:
    rng = random.Random(3)
    right = GAP.platforms[2]

    points = [GAP.random_point((right,), rng) for _ in range(50)]

    assert all(500 <= x <= 700 and y == 0 for x, y in points)


def test_no_platform_with_a_width_is_refused() -> None:
    with pytest.raises(ValueError, match="no platform"):
        replace(GAP, platforms=()).random_point()


def test_the_platform_at_a_point_is_the_one_under_it() -> None:
    floor, shelf = LEDGE.platforms

    assert LEDGE.platform_at((300.0, 0.0)) == floor
    assert LEDGE.platform_at((300.0, -50.0)) == shelf
    assert LEDGE.platform_at((300.0, -40.0)) == shelf  # nearer the shelf
    assert LEDGE.platform_at((100.0, -SURFACE_TOLERANCE)) == floor


def test_a_point_in_the_air_or_over_a_gap_is_on_no_platform() -> None:
    assert LEDGE.platform_at((100.0, -SURFACE_TOLERANCE - 1)) is None
    assert GAP.platform_at((225.0, 0.0)) is None


def test_the_rope_at_a_point_is_the_one_it_hangs_on() -> None:
    """`rope_grab`'s left rope hangs at x 300 from y -198 to -40."""
    world = WorldMap.from_map_data(rope_grab())

    rope = world.rope_at((302.0, -100.0))
    assert rope is not None
    assert rope.x == 300
    assert world.rope_at((300.0, -30.0)) == rope  # 10 px under its bottom
    assert world.rope_at((300.0, 0.0)) is None  # on the floor, 40 px under it
    assert world.rope_at((400.0, -100.0)) is None


def test_the_npcs_are_the_maps_npc_spawns() -> None:
    npc = Spawn("npc", 1012000, "Regular Cab", 120, 0, 1, 100, 140, None, False, False)
    mob = Spawn("mob", 100100, "Snail", 300, 0, 1, 250, 350, 5, False, False)
    data = replace(jump_gap(), spawns=(npc, mob))

    assert WorldMap.from_map_data(data).npcs == (npc,)
