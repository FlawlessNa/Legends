import numpy as np

from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid


def test_replace_nodes_preserves_coordinates_and_grid_id():
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
