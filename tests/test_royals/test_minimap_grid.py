"""
`MinimapGrid._replace_nodes` rebuilds every `GridNode` the pathfinding library
produced as a `MinimapNode`. `GridNode` is a dataclass whose first eight fields are
the finder's scratch state, so the rebuild has to name its arguments: positionally,
the coordinates land in the scratch fields and `__post_init__`'s `cleanup()` wipes
them, leaving every node on its defaults with nothing raised.
"""

import numpy as np
import pytest
from pathfinding.finder.dijkstra import DijkstraFinder

from maple.model.mechanics.maple_map import MapleMap
from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid, MinimapNode

# Walkable/unwalkable and three distinct weights, so a node that silently falls back
# to `walkable=True, weight=0.0` cannot pass by coincidence.
CANVAS = np.array(
    [
        [1, 0, 3],
        [2, 1, 0],
    ]
)

# Real mapfiles under `configs/maps/`. `MysteriousPath3` is excluded: it is a
# legacy-schema file that builds an empty canvas (see issue #10).
MAPFILES = ["GhostShip1", "Line1Area1"]


@pytest.fixture
def grid() -> MinimapGrid:
    return MinimapGrid(CANVAS, speed=1.0, grid_id="test_map")


def test_replace_nodes_preserves_coordinates(grid: MinimapGrid) -> None:
    """
    Every node knows where it is. Positionally, `x` lands in `h` and `y` in `g`, and
    every node reports (0, 0) — pathfinding, the connection builders and
    `path_into_movements`' dx/dy matching all then run on garbage coordinates.
    """
    coordinates = [[(node.x, node.y) for node in row] for row in grid.nodes]
    assert coordinates == [
        [(0, 0), (1, 0), (2, 0)],
        [(0, 1), (1, 1), (2, 1)],
    ]


def test_replace_nodes_preserves_walkable_and_weight(grid: MinimapGrid) -> None:
    assert [[(n.walkable, n.weight) for n in row] for row in grid.nodes] == [
        [(True, 1.0), (False, 0.0), (True, 3.0)],
        [(True, 2.0), (True, 1.0), (False, 0.0)],
    ]


def test_replace_nodes_preserves_grid_id(grid: MinimapGrid) -> None:
    """
    `MapleMinimap.get_node_info` asserts `node.grid_id == self.map_name`, so a dropped
    `grid_id` fails every mapfile at `generate_grid`.
    """
    assert {node.grid_id for row in grid.nodes for node in row} == {"test_map"}


def test_replace_nodes_leaves_finder_scratch_state_at_its_defaults(
    grid: MinimapGrid,
) -> None:
    """
    The inverse of the defect: node data must not leak into the finder's scratch
    fields, which `DijkstraFinder` reads before it writes.
    """
    for row in grid.nodes:
        for node in row:
            assert (node.h, node.g, node.f) == (0.0, 0.0, 0.0)
            assert (node.opened, node.closed) == (0, False)
            assert node.parent is None
            assert node.retain_count == 0
            assert node.tested is False


def test_replace_nodes_produces_minimap_nodes_carrying_the_grid_hash(
    grid: MinimapGrid,
) -> None:
    for row in grid.nodes:
        for node in row:
            assert isinstance(node, MinimapNode)
            assert node.grid_hash == hash(grid)


@pytest.mark.parametrize("map_name", MAPFILES)
@pytest.mark.parametrize("allow_teleport", [False, True])
def test_generate_grid_succeeds_for_checked_in_mapfiles(
    map_name: str, allow_teleport: bool
) -> None:
    """
    The consequence the fix buys: `generate_grid` raised `AssertionError` on every
    mapfile, so nothing offline could build a grid at all.
    """
    minimap = MapleMap(map_name).minimap
    grid = minimap.generate_grid(allow_teleport, 1.0, 1.0)

    assert grid.grid_id == map_name
    assert (grid.width, grid.height) == (
        minimap.modified_minimap.shape[1],
        minimap.modified_minimap.shape[0],
    )
    for y, x in np.argwhere(minimap.modified_minimap):
        node = grid.node(int(x), int(y))
        assert (node.x, node.y) == (int(x), int(y))
        assert node.grid_id == map_name


def test_a_path_can_be_computed_offline() -> None:
    """
    The movement lab's precondition: a Path between two walkable nodes of a real map.
    Only that one exists and runs on real coordinates is pinned here — whether it is
    a *sensible* route has no offline oracle (issue #9).
    """
    minimap = MapleMap("GhostShip1").minimap
    grid = minimap.generate_grid(True, 1.0, 1.0)
    walkable = [(int(x), int(y)) for y, x in np.argwhere(minimap.modified_minimap)]
    start, end = walkable[0], walkable[len(walkable) // 2]

    path, _ = DijkstraFinder().find_path(grid.node(*start), grid.node(*end), grid)

    assert (path[0].x, path[0].y) == start
    assert (path[-1].x, path[-1].y) == end
