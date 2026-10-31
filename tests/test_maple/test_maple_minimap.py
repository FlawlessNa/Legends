import numpy as np

from maple.model.mechanics.maple_map import MapleMinimap
from maple.model.mechanics.minimap_creation.minimap_edits_model import (
    MinimapEditsManager,
)


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


# --- The map file's optional map_id (R7) ---------------------------------------

_FILE = {
    "_meta": {
        "scale_x": 0.06,
        "scale_y": 0.05,
        "canvas_width": 40,
        "canvas_height": 20,
    },
    "title_img_path": "maple/assets/detection_images/OldMinimap.png",
    "mobs": [],
    "features": {"floor": {"left": 1, "right": 30, "top": 15, "bottom": 15}},
    "portals": [],
}


def test_a_map_file_without_a_map_id_is_still_valid() -> None:
    edits = MinimapEditsManager.from_dict(_FILE)

    assert edits.map_id is None
    assert MapleMinimap("Old", edits).map_id is None
    assert "map_id" not in edits.to_dict()


def test_a_map_files_map_id_is_read_and_written_back() -> None:
    edits = MinimapEditsManager.from_dict({**_FILE, "map_id": 100000000})

    assert edits.map_id == 100000000
    assert MapleMinimap("New", edits).map_id == 100000000
    assert MinimapEditsManager.from_dict(edits.to_dict()).map_id == 100000000


def test_the_map_model_reads_nothing_off_the_screen() -> None:
    minimap = MapleMinimap("Old", MinimapEditsManager.from_dict(_FILE))

    assert type(minimap).__mro__ == (MapleMinimap, object)
    assert (minimap.map_area_width, minimap.map_area_height) == (40, 20)
