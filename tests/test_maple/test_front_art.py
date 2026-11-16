"""
`FrontArt` (#517): what of a map is drawn over a character on a given layer,
from hand-built layer items and from the synthetic client of
`tests/test_game_data/test_render.py`; and `WorldMap.layer_near`, the layer a
character near a point is drawn on.
"""

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from game_data.catalogue import (
    Bounds,
    Catalogue,
    Foothold,
    LayerFrame,
    MapLayer,
    Rope,
    build_catalogue,
)
from game_data.extraction import extract
from game_data.render import render_map
from maple.model.world import FrontArt, Platform, WorldMap
from tests.test_game_data.test_render import LAYERS, LAYERS_VR, write_render_client


def block(width: int, height: int, alpha: int = 255) -> NDArray[np.uint8]:
    pixels = np.zeros((height, width, 4), np.uint8)
    pixels[..., 3] = alpha
    return pixels


def item(
    layer: int | None,
    x: int,
    y: int,
    *frames: tuple[str, int, int],
    flip: bool = False,
    kind: str = "object",
) -> MapLayer:
    return MapLayer(
        kind,
        layer,
        0,
        0,
        x,
        y,
        flip,
        "asset",
        tuple(
            LayerFrame(n, name, ox, oy, None) for n, (name, ox, oy) in enumerate(frames)
        ),
        None,
    )


def test_only_the_layers_above_a_characters_are_in_front_of_it() -> None:
    images = {"wide": block(4, 2)}
    art = FrontArt.from_layers(
        [item(1, 10, 20, ("wide", 0, 0)), item(2, 30, 20, ("wide", 0, 0))],
        images.__getitem__,
    )

    on_1 = art.covered(1, (0, 0, 40, 30))
    on_0 = art.covered(0, (0, 0, 40, 30))

    assert on_1.shape == (30, 40)
    assert np.argwhere(on_1).tolist() == [
        [y, x] for y in (20, 21) for x in range(30, 34)
    ]
    assert on_0.sum() == 16  # both
    assert not art.covered(2, (0, 0, 40, 30)).any()


def test_an_item_is_placed_by_its_origin_and_mirrored_when_flipped() -> None:
    """A 3x1 image with its left pixel transparent, origin (1, 0): unflipped
    it draws at x 10 and 11; flipped, its image mirrored and its left edge at
    x - (width - origin x), at 8 and 9, as `game_data.render` draws it."""
    image = block(3, 1)
    image[0, 0, 3] = 0
    images = {"bar": image}

    plain = FrontArt.from_layers([item(1, 10, 5, ("bar", 1, 0))], images.__getitem__)
    flipped = FrontArt.from_layers(
        [item(1, 10, 5, ("bar", 1, 0), flip=True)], images.__getitem__
    )

    assert np.flatnonzero(plain.covered(0, (0, 5, 20, 6))[0]).tolist() == [10, 11]
    assert np.flatnonzero(flipped.covered(0, (0, 5, 20, 6))[0]).tolist() == [8, 9]


def test_an_animated_item_covers_every_frames_pixels() -> None:
    images = {"a": block(1, 1), "b": block(1, 1)}
    art = FrontArt.from_layers(
        [item(1, 10, 10, ("a", 0, 0), ("b", 0, 1))], images.__getitem__
    )

    assert np.argwhere(art.covered(0, (10, 9, 11, 11))).tolist() == [[0, 0], [1, 0]]


def test_soft_edges_count_and_backgrounds_do_not() -> None:
    images = {"faint": block(1, 1, alpha=1), "solid": block(5, 5)}
    back = MapLayer(
        "back",
        None,
        0,
        None,
        0,
        0,
        False,
        "b",
        (LayerFrame(0, "solid", 0, 0, None),),
        None,
    )
    art = FrontArt.from_layers(
        [item(1, 2, 2, ("faint", 0, 0)), back], images.__getitem__
    )

    assert np.argwhere(art.covered(0, (0, 0, 5, 5))).tolist() == [[2, 2]]


def test_a_box_partly_off_an_item_takes_only_the_overlap() -> None:
    art = FrontArt.from_layers(
        [item(1, 10, 10, ("big", 0, 0))], {"big": block(10, 10)}.__getitem__
    )

    mask = art.covered(0, (5, 5, 15, 15))

    assert mask[:5].sum() == 0
    assert mask[:, :5].sum() == 0
    assert mask[5:, 5:].all()


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("front")
    root = base / "store"
    extract(write_render_client(base / "Data"), root, catalogue=build_catalogue)
    return root


def test_loaded_from_a_store_it_covers_what_the_items_render_draws(root: Path) -> None:
    """Every frame of every tile and object of the synthetic client's layered
    map, against the renderer's own drawing of them."""
    with Catalogue.latest(root) as cat:
        build = cat.build
        items = [i for i in cat.map_layers(LAYERS) if i.background is None]
        frames = max(len(i.frames) for i in items)
        drawn = np.zeros(
            (LAYERS_VR[3] - LAYERS_VR[1], LAYERS_VR[2] - LAYERS_VR[0]), bool
        )
        for frame in range(frames):
            screen = render_map(
                cat, LAYERS, frame=frame, keep=lambda i: i.background is None
            )
            drawn |= screen[..., 3] > 0
        layer_1 = render_map(cat, LAYERS, keep=lambda i: i.layer == 1)[..., 3] > 0

    art = FrontArt.load(build, LAYERS, root)

    assert frames == 2
    assert np.array_equal(art.covered(-1, LAYERS_VR), drawn)
    assert np.array_equal(art.covered(0, LAYERS_VR), layer_1)
    assert layer_1.sum() == 1


# --- the layer a character is drawn on ---------------------------------------


def surfaces(
    *platforms: tuple[int, int, int, int], ropes: tuple[Rope, ...] = ()
) -> WorldMap:
    """Platforms `(layer, left, right, y)`, flat."""
    return WorldMap(
        1,
        None,
        None,
        Bounds(-500, -500, 500, 500),
        None,
        tuple(
            Platform(layer, (Foothold("map", layer, 0, n, left, y, right, y, 0, 0),))
            for n, (layer, left, right, y) in enumerate(platforms, start=1)
        ),
        (),
        ropes,
        (),
    )


def test_the_layer_near_is_the_lowest_of_the_platforms_and_ropes_within_reach() -> None:
    world = surfaces(
        (3, 0, 100, 0),
        (5, 0, 100, 20),
        (1, 0, 100, 200),  # far below
        ropes=(Rope("map", 1, 110, 0, 50, True, True, 4),),
    )

    assert world.layer_near((50, 0), 32) == 3
    assert world.layer_near((50, 0), 10) == 3
    assert world.layer_near((50, 24), 10) == 5
    assert world.layer_near((105, 30), 10) == 4  # the ladder's page, past the edges
    assert world.layer_near((95, 0), 32) == 3


def test_no_layer_away_from_every_surface_or_where_none_says_its_own() -> None:
    world = surfaces(
        (2, 0, 100, 0), ropes=(Rope("map", 1, 300, 0, 50, None, None, None),)
    )

    assert world.layer_near((50, -100), 32) is None
    assert world.layer_near((150, 0), 32) is None
    assert world.layer_near((300, 20), 32) is None
