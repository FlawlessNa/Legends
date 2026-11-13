"""
`FootholdGraph` on the real client's maps, from the latest extraction in the
store (`python -m game_data extract`). Marked `client_files`; run with
`pytest -m client_files`. The benchmark is also `lab`: run it with
`pytest -m lab`; it records its number as `graph_longest_ms` (`--junitxml`).
"""

import time
from collections.abc import Callable, Iterator

import pytest

from game_data.catalogue import Rope
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import (
    Direction,
    FootholdGraph,
    MoveKind,
    Point,
    Surface,
)
from maple.model.world import Platform, WorldMap

pytestmark = pytest.mark.client_files

MAPS = ("Dungeon: Damp Forest", "Victoria Road: Ellinia")

#: Platform pairs with no path, by each platform's first foothold ID: from
#: the key, none of the values is reached. In Damp Forest the way up from the
#: floor (23, 79), the low ledge (61) and the rope-top ledge (49) to the
#: middle ledges (70, 76) and the top (36, 44 to 47) is jumping between the
#: hanging ropes, whose tops are no platform (`uf` 0); the graph, like
#: the retired minimap grid, starts a jump off a rope at the top of its arc
#: (`ROPE_JUMP_SPEED` 0), so a jump from rope to rope always loses height.
NO_PATH = {
    "Victoria Road: Ellinia": {},
    "Dungeon: Damp Forest": {
        23: [36, 44, 45, 46, 47, 70, 76],
        49: [36, 44, 45, 46, 47, 70, 76],
        61: [36, 44, 45, 46, 47, 70, 76],
        70: [36, 44, 45, 46, 47],
        76: [36, 44, 45, 46, 47, 70],
        79: [36, 44, 45, 46, 47, 70, 76],
    },
}


@pytest.fixture(scope="module")
def physics() -> VRPhysics:
    return VRPhysics.load()


@pytest.fixture(scope="module", params=MAPS)
def name(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture(scope="module")
def world(name: str) -> WorldMap:
    return WorldMap.load(name)


@pytest.fixture(scope="module")
def graph(world: WorldMap, physics: VRPhysics) -> FootholdGraph:
    return FootholdGraph.build(world, physics)


def middle(platform: Platform) -> Point:
    x = (platform.left + platform.right) / 2
    y = platform.y_at(x)
    assert y is not None
    return (x, y)


def on(point: Point, surface: Surface) -> bool:
    """Whether `point` lies on one of the platform's footholds, or on the rope."""
    x, y = point
    if isinstance(surface, Rope):
        top, bottom = min(surface.y1, surface.y2), max(surface.y1, surface.y2)
        return x == surface.x and top - 1e-6 <= y <= bottom + 1e-6
    for f in surface.footholds:
        if min(f.x1, f.x2) - 1e-6 <= x <= max(f.x1, f.x2) + 1e-6:
            line = f.y1 + (f.y2 - f.y1) * (x - f.x1) / (f.x2 - f.x1)
            if abs(line - y) <= 1e-6:
                return True
    return False


def take_off(surface: Surface, coord: float) -> Point:
    if isinstance(surface, Rope):
        return (surface.x, coord)
    y = surface.y_at(coord)
    assert y is not None
    return (coord, y)


def test_every_stored_move_starts_and_ends_on_a_foothold_or_a_rope(
    graph: FootholdGraph,
) -> None:
    assert graph.moves
    for m in graph.moves:
        assert on(take_off(m.source, m.low), m.source), m
        assert on(take_off(m.source, m.high), m.source), m
        assert on(m.landing_low, m.target), m
        assert on(m.landing_high, m.target), m


def queries(world: WorldMap) -> Iterator[tuple[Point, Point]]:
    """Every platform to every seventh platform, both ways."""
    points = [middle(p) for p in world.platforms]
    for i, start in enumerate(points):
        for goal in points[i % 7 :: 7]:
            yield start, goal
            yield goal, start


def test_every_move_of_a_path_starts_and_ends_on_a_foothold_or_a_rope(
    world: WorldMap, graph: FootholdGraph
) -> None:
    found = 0
    for start, goal in queries(world):
        path = graph.path(start, goal)
        if path is None:
            continue
        found += 1
        if not path.moves:
            assert start == goal
            continue
        assert path.moves[0].start == pytest.approx(start)
        assert path.moves[-1].end == pytest.approx(goal)
        for before, after in zip(path.moves, path.moves[1:], strict=False):
            assert before.end == after.start
        for m in path.moves:
            assert on(m.start, m.start_on), m
            assert on(m.end, m.end_on), m
    assert found


def test_the_platform_pairs_with_no_path_are_the_known_ones(
    name: str, world: WorldMap, graph: FootholdGraph
) -> None:
    missing: dict[int, list[int]] = {}
    for p in world.platforms:
        reached = set(graph.reachable(middle(p)))
        lost = sorted(q.footholds[0].id for q in world.platforms if q not in reached)
        if lost:
            missing[p.footholds[0].id] = lost

    assert missing == NO_PATH[name]


def test_ellinia_bottom_to_top_takes_the_portal_and_ropes() -> None:
    world = WorldMap.load("Victoria Road: Ellinia")
    graph = FootholdGraph.build(world, VRPhysics.load())
    lowest = max(world.platforms, key=lambda p: middle(p)[1])
    highest = min(world.platforms, key=lambda p: middle(p)[1])

    path = graph.path(middle(lowest), middle(highest))

    assert path is not None
    kinds = {m.kind.value for m in path.moves}
    assert {"portal", "climb", "jump"} <= kinds


# --- the benchmark ---------------------------------------------------------------

#: #302's acceptance criterion 6: a path on Ellinia in under 20 ms. It replaced
#: the comparison with the minimap grid, which #399 retired with the map files.
LONGEST_QUERY_S = 0.020


def best_of(runs: int, query: object) -> float:
    assert callable(query)
    times = []
    for _ in range(runs):
        began = time.perf_counter()
        query()
        times.append(time.perf_counter() - began)
    return min(times)


@pytest.mark.lab
def test_the_graphs_longest_query_on_ellinia_takes_under_20_ms(
    physics: VRPhysics, record_property: Callable[[str, object], None]
) -> None:
    world = WorldMap.load("Victoria Road: Ellinia")
    graph = FootholdGraph.build(world, physics)
    lowest = max(world.platforms, key=lambda p: middle(p)[1])
    highest = min(world.platforms, key=lambda p: middle(p)[1])
    longest = 0.0
    for p in world.platforms:
        for start, goal in ((middle(lowest), middle(p)), (middle(p), middle(highest))):
            longest = max(longest, best_of(3, lambda s=start, g=goal: graph.path(s, g)))

    record_property("graph_longest_ms", round(1000 * longest, 1))
    assert longest < LONGEST_QUERY_S, (
        f"FootholdGraph's longest query {1000 * longest:.1f} ms"
    )


def test_no_path_between_joined_platforms_holds_a_jump_that_saves_no_time(
    graph: FootholdGraph,
) -> None:
    """A trip of 120 px centred on each join, from one platform to the other."""
    trips = 0
    for join in (m for m in graph.moves if m.kind is MoveKind.WALK):
        x, y = join.landing_low
        sign = 1 if join.direction is Direction.RIGHT else -1
        start, goal = (x - 60 * sign, y), (x + 60 * sign, y)
        try:
            path = graph.path(start, goal)
        except ValueError:
            continue  # a point that lies on no surface
        if (
            path is None
            or path.moves[0].start_on != join.source
            or path.moves[-1].end_on != join.target
        ):
            continue
        trips += 1
        assert MoveKind.JUMP not in {m.kind for m in path.moves}, (join, path)
    # Damp Forest has no joins; Ellinia's are flat and plentiful.
    assert trips or not any(m.kind is MoveKind.WALK for m in graph.moves)
