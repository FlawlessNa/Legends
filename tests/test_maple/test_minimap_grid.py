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
from maple.model.mechanics.minimap_creation.minimap_grid import (
    ConnectionTypes,
    MinimapGrid,
    MinimapNode,
)

# Walkable/unwalkable and three distinct weights, so a node that silently falls back
# to `walkable=True, weight=0.0` cannot pass by coincidence.
CANVAS = np.array(
    [
        [1, 0, 3],
        [2, 1, 0],
    ]
)

# Every real mapfile under `configs/maps/`. `MysteriousPath3` used to be a third:
# a legacy-schema file that built an empty canvas, deleted by issue #103.
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


def test_replace_nodes_preserves_coordinates_and_grid_id() -> None:
    """
    `MinimapGrid._replace_nodes` swaps every base `GridNode` for a `MinimapNode`.
    `MinimapNode` is a dataclass inheriting fields (h, g, f, opened, closed, parent,
    retain_count, tested) from `Node` ahead of (x, y, walkable, weight, grid_id,
    connections) from `GridNode`, so positional construction silently binds `x` into
    `h`, `y` into `g`, etc., leaving `x`, `y` and `grid_id` at their dataclass
    defaults (0, 0, None) instead of the values being copied.
    """
    canvas = np.ones((4, 5), dtype=np.uint8)
    grid = MinimapGrid(canvas, speed=1.0, grid_id="TestMap")

    node = grid.node(3, 2)

    assert (node.x, node.y) == (3, 2)
    assert node.grid_id == "TestMap"


# --- The `neighbors` / `adjacent_nodes` split (issue #107) -------------------------
#
# `MinimapGrid.neighbors` used to override the base with a *different* fourth
# parameter — `include_connections: bool = True` where the base declares
# `include_non_walkables: bool = False`. Two consequences: `include_non_walkables`
# was unreachable through a `MinimapGrid` at all, and any positional fourth argument
# silently changed meaning across the override. The two flags answer different
# questions, so they are now different methods: `neighbors` is the pathfinder's and
# belongs to the base class untouched, `adjacent_nodes` is the geometric one.


@pytest.fixture
def open_grid() -> MinimapGrid:
    """
    5x5, fully walkable except (2, 1), which sits directly above the centre node the
    assertions below are all written about.
    """
    canvas = np.ones((5, 5), dtype=np.uint8)
    canvas[1, 2] = 0
    return MinimapGrid(canvas, speed=1.0, grid_id="open_map")


def test_include_non_walkables_is_reachable_through_a_minimap_grid(
    open_grid: MinimapGrid,
) -> None:
    """
    The ticket's headline defect. The override occupied slot 4 with a flag of its
    own, so the base's `include_non_walkables` could not be reached by keyword *or*
    at all: this call used to raise `TypeError`.
    """
    centre = open_grid.node(2, 2)

    walkable_only = open_grid.neighbors(centre)
    with_unwalkable = open_grid.neighbors(centre, include_non_walkables=True)

    assert (2, 1) not in [(n.x, n.y) for n in walkable_only]
    assert (2, 1) in [(n.x, n.y) for n in with_unwalkable]


def test_neighbors_keeps_connections_and_adjacent_nodes_drops_them(
    open_grid: MinimapGrid,
) -> None:
    """
    The split itself. The pathfinder needs connections — they are edges in the search
    graph. The four geometric call sites need them gone.
    """
    centre = open_grid.node(2, 2)
    far = open_grid.node(4, 4)
    centre.connect(far, ConnectionTypes.JUMP)

    assert far in open_grid.neighbors(centre)
    assert far not in open_grid.adjacent_nodes(centre)
    assert far not in open_grid.adjacent_nodes(centre, diagonal=True)


def test_adjacent_nodes_is_orthogonal_by_default(open_grid: MinimapGrid) -> None:
    """
    `path_into_movements` relies on the default: it asks whether the next Path node
    touches the current one, and a diagonal step is *not* a walk. The old call site
    got this from `neighbors`' own `DiagonalMovement.never` default, so widening it
    here would silently reclassify diagonal steps.
    """
    adjacent = {(n.x, n.y) for n in open_grid.adjacent_nodes(open_grid.node(2, 2))}

    assert adjacent == {(1, 2), (3, 2), (2, 3)}  # (2, 1) is unwalkable


def test_adjacent_nodes_widens_to_eight_cells_when_diagonal(
    open_grid: MinimapGrid,
) -> None:
    """
    What `is_left_edge` and `is_right_edge` ask for: a node with a walkable cell
    diagonally below-left is not a left edge.
    """
    adjacent = {
        (n.x, n.y)
        for n in open_grid.adjacent_nodes(open_grid.node(2, 2), diagonal=True)
    }

    assert adjacent == {
        (1, 1),
        (3, 1),
        (1, 2),
        (3, 2),
        (1, 3),
        (2, 3),
        (3, 3),
    }  # (2, 1) is unwalkable


def test_edge_detection_survives_the_split(open_grid: MinimapGrid) -> None:
    """
    `is_left_edge` / `is_right_edge` moved from a three-argument `neighbors` call to
    `adjacent_nodes(diagonal=True)`; the answers must not move with them.
    """
    assert open_grid.is_left_edge(open_grid.node(0, 2))
    assert not open_grid.is_left_edge(open_grid.node(2, 2))
    assert open_grid.is_right_edge(open_grid.node(4, 2))
    assert not open_grid.is_right_edge(open_grid.node(2, 2))
