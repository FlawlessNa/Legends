"""
`FootholdGraph` on the real client's maps, from the latest extraction in the
store (`python -m game_data extract`). Marked `client_files`; run with
`pytest -m client_files`. The benchmark is also `lab`: run it with
`pytest -m lab`; it records its numbers as
`grid_ms` and `graph_longest_ms` (`--junitxml`).
"""

import time
from collections import deque
from collections.abc import Callable, Iterator

import numpy as np
import pytest
from pathfinding.finder.dijkstra import DijkstraFinder

from game_data.catalogue import Rope
from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraph, Point, Surface
from maple.model.world import Platform, WorldMap

pytestmark = pytest.mark.client_files

MAPS = ("Dungeon: Damp Forest", "Victoria Road: Ellinia")

#: Platform pairs with no path, by each platform's first foothold ID: from
#: the key, none of the values is reached. In Damp Forest the way up from the
#: floor (23, 79), the low ledge (61) and the rope-top ledge (49) to the
#: middle ledges (70, 76) and the top (36, 44 to 47) is jumping between the
#: hanging ropes, whose tops are no platform (`uf` 0); the graph, like
#: today's grid, starts a jump off a rope at the top of its arc
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


# --- the benchmark against today's grid -------------------------------------

#: Virtual px per grid cell: today's minimap scale.
CELL = 16


def rasterise(world: WorldMap) -> np.ndarray:
    """The map's platforms and ropes drawn into cells of `CELL` virtual px."""
    b = world.bounds
    left = min(b.left, *(p.left for p in world.platforms))
    top = min(b.top, *(min(f.y1, f.y2) for p in world.platforms for f in p.footholds))
    right = max(b.right, *(p.right for p in world.platforms))
    bottom = max(
        b.bottom, *(max(f.y1, f.y2) for p in world.platforms for f in p.footholds)
    )
    canvas = np.zeros(
        ((bottom - top) // CELL + 2, (right - left) // CELL + 2), np.uint8
    )
    for p in world.platforms:
        for f in p.footholds:
            for x in np.arange(min(f.x1, f.x2), max(f.x1, f.x2) + 1):
                y = f.y1 + (f.y2 - f.y1) * (x - f.x1) / (f.x2 - f.x1)
                canvas[int(y - top) // CELL, int(x - left) // CELL] = 1
    for r in world.ropes:
        for y in range(min(r.y1, r.y2), max(r.y1, r.y2) + 1):
            canvas[(y - top) // CELL, (r.x - left) // CELL] = 1
    return canvas


def farthest_pair(canvas: np.ndarray) -> tuple[tuple[int, int], tuple[int, int]]:
    """The largest connected set of cells, and two cells of it far apart."""
    seen = np.zeros_like(canvas, dtype=bool)
    best: list[tuple[int, int]] = []
    for y, x in zip(*np.nonzero(canvas), strict=True):
        if seen[y, x]:
            continue
        group = [(int(x), int(y))]
        seen[y, x] = True
        todo = deque(group)
        while todo:
            cx, cy = todo.popleft()
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if (
                    0 <= ny < canvas.shape[0]
                    and 0 <= nx < canvas.shape[1]
                    and canvas[ny, nx]
                    and not seen[ny, nx]
                ):
                    seen[ny, nx] = True
                    group.append((nx, ny))
                    todo.append((nx, ny))
        if len(group) > len(best):
            best = group
    start = max(best, key=lambda c: c[1])
    goal = max(best, key=lambda c: abs(c[0] - start[0]) + abs(c[1] - start[1]))
    return start, goal


def best_of(runs: int, query: object) -> float:
    assert callable(query)
    times = []
    for _ in range(runs):
        began = time.perf_counter()
        query()
        times.append(time.perf_counter() - began)
    return min(times)


@pytest.mark.lab
def test_the_graphs_longest_query_on_ellinia_is_no_slower_than_todays_grid(
    physics: VRPhysics, record_property: Callable[[str, object], None]
) -> None:
    world = WorldMap.load("Victoria Road: Ellinia")
    canvas = rasterise(world)
    grid = MinimapGrid(canvas, speed=physics.walk_speed / CELL)
    (sx, sy), (gx, gy) = farthest_pair(canvas)

    def grid_query() -> None:
        path, _ = DijkstraFinder().find_path(grid.node(sx, sy), grid.node(gx, gy), grid)
        grid.cleanup()
        assert path

    baseline = best_of(3, grid_query)

    graph = FootholdGraph.build(world, physics)
    lowest = max(world.platforms, key=lambda p: middle(p)[1])
    highest = min(world.platforms, key=lambda p: middle(p)[1])
    longest = 0.0
    for p in world.platforms:
        for start, goal in ((middle(lowest), middle(p)), (middle(p), middle(highest))):
            longest = max(longest, best_of(3, lambda s=start, g=goal: graph.path(s, g)))

    record_property("grid_ms", round(1000 * baseline, 1))
    record_property("graph_longest_ms", round(1000 * longest, 1))
    assert longest <= baseline, (
        f"grid ({canvas.shape[1]}x{canvas.shape[0]} cells of {CELL} px) "
        f"{1000 * baseline:.1f} ms; FootholdGraph's longest query {1000 * longest:.1f} ms"
    )
