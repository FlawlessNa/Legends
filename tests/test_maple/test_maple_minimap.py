import numpy as np

from maple.model.mechanics.maple_map import MapleMinimap


def _minimap_with_single_walkable_node() -> MapleMinimap:
    """
    A `MapleMinimap` whose only reachable state is `modified_minimap`.

    `__init__` needs a `MinimapEditsManager` and a canvas to build one, none of which
    `random_point` reads, so the instance is built without it.
    """
    minimap = object.__new__(MapleMinimap)
    canvas = np.zeros((10, 10), dtype=np.uint8)
    canvas[3, 7] = 1
    minimap.modified_minimap = canvas
    return minimap


def test_random_point_returns_the_only_walkable_node() -> None:
    minimap = _minimap_with_single_walkable_node()
    assert minimap.random_point() == (7, 3)


def test_random_point_returns_builtin_ints() -> None:
    """
    `np.argwhere` yields `np.int64`. A random point is a Minimap Position like any
    other and must be a builtin `int` before it reaches a telemetry payload.
    """
    x, y = _minimap_with_single_walkable_node().random_point()
    assert type(x) is int
    assert type(y) is int
