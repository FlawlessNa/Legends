"""
`maple.model.world`: platforms chained from hand-built footholds, `WorldMap`
from hand-built `MapData`, and the static render from a synthetic client
(`tests/test_game_data/test_render.py`'s), cached in a temporary folder.
"""

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from game_data.catalogue import (
    Bounds,
    Catalogue,
    Foothold,
    MapData,
    Minimap,
    Portal,
    Rope,
    build_catalogue,
)
from game_data.extraction import extract
from game_data.render import render_map
from maple.model.world import (
    MinimapTransform,
    Platform,
    StaticRender,
    WorldMap,
    chain_platforms,
)
from maple.model.world.static_render import MOVING_MARGIN
from tests.test_game_data.test_render import (
    BACKGROUNDS,
    BACKGROUNDS_VR,
    LAYERS,
    LAYERS_VR,
    write_render_client,
)


def fh(
    fh_id: int,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    prev: int = 0,
    next: int = 0,
    *,
    layer: int = 0,
) -> Foothold:
    return Foothold("map", layer, 1, fh_id, x1, y1, x2, y2, prev, next)


def ids(platforms: Iterable[Platform]) -> list[list[int]]:
    return [[f.id for f in p.footholds] for p in platforms]


# --- chaining ----------------------------------------------------------------


def test_footholds_linked_by_prev_and_next_are_one_platform_slopes_included() -> None:
    platforms, walls = chain_platforms(
        [fh(2, 10, 0, 20, -5, 1, 3), fh(1, 0, 0, 10, 0, 0, 2), fh(3, 20, -5, 30, -5, 2)]
    )

    assert ids(platforms) == [[1, 2, 3]]
    assert walls == ()
    assert (platforms[0].left, platforms[0].right) == (0, 30)
    assert platforms[0].y_at(15) == -2.5
    assert platforms[0].y_at(31) is None


def test_unlinked_footholds_are_platforms_of_their_own() -> None:
    platforms, _ = chain_platforms([fh(1, 0, 0, 10, 0), fh(2, 20, 0, 30, 0)])

    assert ids(platforms) == [[1], [2]]


def test_a_wall_is_on_no_platform_and_splits_the_chain_it_meets() -> None:
    """1 -> 2 (a wall) -> 3: the wall is left out, and 1 and 3 aren't joined."""
    wall = fh(2, 10, 0, 10, -20, 1, 3)
    platforms, walls = chain_platforms(
        [fh(1, 0, 0, 10, 0, 0, 2), wall, fh(3, 10, -20, 30, -20, 2)]
    )

    assert ids(platforms) == [[1], [3]]
    assert walls == (wall,)


def test_a_chain_never_crosses_layers() -> None:
    """2 names 1 in both directions, but they are in different layers; IDs
    are looked up within a layer, so 2's `prev` names layer 1's 1."""
    platforms, _ = chain_platforms(
        [
            fh(1, 0, 0, 10, 0, 0, 2, layer=0),
            fh(2, 10, 0, 20, 0, 1, 0, layer=1),
            fh(1, -10, 0, 10, 0, 0, 2, layer=1),
        ]
    )

    assert sorted(ids(platforms)) == [[1], [1, 2]]
    assert {p.layer for p in platforms if len(p.footholds) == 2} == {1}


def test_a_link_to_a_foothold_that_does_not_exist_ends_the_chain() -> None:
    platforms, _ = chain_platforms(
        [fh(1, 0, 0, 10, 0, 9, 2), fh(2, 10, 0, 20, 0, 1, 8)]
    )

    assert ids(platforms) == [[1, 2]]


def test_a_one_sided_link_joins_nothing_so_a_fork_stays_two_chains() -> None:
    """1's `next` is 2, but 3 also names 1 as its `prev` (a fork, as Ellinia
    has): only the link both sides agree on counts."""
    platforms, _ = chain_platforms(
        [fh(1, 0, 0, 10, 0, 0, 2), fh(2, 10, 0, 20, 0, 1), fh(3, 10, 0, 20, 1, 1)]
    )

    assert ids(platforms) == [[1, 2], [3]]


def test_every_foothold_is_on_exactly_one_platform_however_the_links_break() -> None:
    footholds = [
        fh(1, 0, 0, 10, 0, 5, 2),
        fh(2, 10, 0, 20, 0, 4, 3),
        fh(3, 20, 0, 30, 0, 2, 1),
        fh(4, 30, 0, 40, 0, 3, 7),
        fh(5, 40, 0, 50, 0, 1, 1),
    ]
    platforms, _ = chain_platforms(footholds)

    placed = sorted(f.id for p in platforms for f in p.footholds)
    assert placed == [1, 2, 3, 4, 5]


def test_a_chain_that_closes_on_itself_is_opened_before_its_lowest_id() -> None:
    platforms, _ = chain_platforms(
        [fh(3, 20, 0, 0, 0, 2, 1), fh(1, 0, 0, 10, 0, 3, 2), fh(2, 10, 0, 20, 0, 1, 3)]
    )

    assert ids(platforms) == [[1, 2, 3]]


# --- WorldMap from MapData ---------------------------------------------------


def map_data(**changes: object) -> MapData:
    data = MapData(
        id=7,
        name="Somewhere",
        street="Test Road",
        vr=Bounds(-100, -200, 300, 50),
        vr_derived=False,
        minimap=Minimap(100, 200, 4, 400, 250),
        town=False,
        swim=False,
        fly=False,
        field_limit=0,
        bgm=None,
        return_map=None,
        footholds=(
            fh(1, 0, 0, 10, 0, 0, 2),
            fh(2, 10, 0, 10, -30, 1, 0),
            Foothold("object", None, None, 0, 0, 0, 10, 0, None, None),
            Foothold("tile", None, None, 1, 50, 0, 50, -10, None, None),
        ),
        ropes=(Rope("map", 1, 5, -40, 0, True, False, 0),),
        portals=(Portal("sp", 0, 3, 0, None, None),),
        spawns=(),
    )
    return replace(data, **changes)


def test_a_world_map_holds_the_maps_geometry_from_its_map_data() -> None:
    data = map_data()
    world = WorldMap.from_map_data(data)

    assert (world.id, world.name, world.street) == (7, "Somewhere", "Test Road")
    assert world.bounds == Bounds(-100, -200, 300, 50)
    assert ids(world.platforms) == [[1]]
    assert [w.id for w in world.walls] == [2]
    assert world.ropes == data.ropes
    assert world.ropes[0].usable_from_foothold is False
    assert world.ropes[0].ladder is True
    assert world.portals == data.portals
    assert world.static_render is None


def test_footholds_drawn_on_objects_and_tiles_are_neither_platforms_nor_walls() -> None:
    world = WorldMap.from_map_data(map_data())

    sources = {f.source for p in world.platforms for f in p.footholds}
    assert sources | {w.source for w in world.walls} == {"map"}


def test_ropes_drawn_on_objects_are_left_out() -> None:
    own = Rope("map", 1, 5, -40, 0, True, False, 0)
    drawn = Rope("object", 0, 8, -40, 0, None, None, None)

    world = WorldMap.from_map_data(map_data(ropes=(own, drawn)))

    assert world.ropes == (own,)


def test_the_minimap_transform_converts_canvas_and_virtual_px() -> None:
    world = WorldMap.from_map_data(map_data())

    assert world.minimap == MinimapTransform((100, 200), 4)
    assert world.minimap is not None
    assert world.minimap.scale == 16
    assert world.minimap.to_virtual((10, 20)) == (60, 120)
    assert world.minimap.to_canvas((60, 120)) == (10, 20)


def test_a_map_without_a_minimap_has_no_transform() -> None:
    assert WorldMap.from_map_data(map_data(minimap=None)).minimap is None


# --- loading, and the static render -----------------------------------------


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("world")
    root = base / "store"
    extract(write_render_client(base / "Data"), root, catalogue=build_catalogue)
    return root


def test_load_reads_the_map_from_the_latest_extraction(
    root: Path, tmp_path: Path
) -> None:
    world = WorldMap.load("Test Road: Layers", root=root, cache=tmp_path)

    assert world.id == LAYERS
    assert world.bounds == Bounds(*LAYERS_VR)
    assert [[f.source for f in p.footholds] for p in world.platforms] == [["map"]]
    assert [r.x for r in world.ropes] == [270]
    assert [p.name for p in world.portals] == ["sp"]
    with Catalogue.latest(root) as cat:
        build = cat.build
    assert world.static_render == StaticRender(build, LAYERS, root, tmp_path)
    assert not list(tmp_path.iterdir()), "nothing is drawn until it's asked for"


def static_render(root: Path, cache: Path, map_id: int) -> StaticRender:
    render = WorldMap.load(map_id, root=root, cache=cache).static_render
    assert render is not None
    return render


def at(pixels: np.ndarray, x: int, y: int, vr: tuple[int, int, int, int]) -> int:
    """The alpha at virtual `(x, y)`."""
    return int(pixels[y - vr[1], x - vr[0], 3])


def test_the_static_render_leaves_out_what_moves_and_the_pixels_around_it(
    root: Path, tmp_path: Path
) -> None:
    """The animated object at (120, 0) is gone, with `MOVING_MARGIN` around
    it; the tiles and the still objects are drawn as `render_map` draws them."""
    pixels = static_render(root, tmp_path, LAYERS).pixels()
    with Catalogue.latest(root) as cat:
        full = render_map(cat, LAYERS)

    assert pixels.shape == full.shape
    assert at(full, 120, 0, LAYERS_VR) == 255
    for dx in (-MOVING_MARGIN, 0, MOVING_MARGIN):
        assert at(pixels, 120 + dx, 0, LAYERS_VR) == 0
    still = (slice(None), slice(None, 120 - MOVING_MARGIN - LAYERS_VR[0]))
    assert np.array_equal(pixels[still], full[still])


def test_the_static_render_keeps_only_opaque_backgrounds_fixed_to_the_map(
    root: Path, tmp_path: Path
) -> None:
    pixels = static_render(root, tmp_path, BACKGROUNDS).pixels()

    assert at(pixels, 11, 11, BACKGROUNDS_VR) == 255  # rx -100, opaque
    assert at(pixels, 110, 60, BACKGROUNDS_VR) == 0  # rx 0: moves with the camera
    assert at(pixels, 60, 35, BACKGROUNDS_VR) == 0  # rx -50: parallax
    assert at(pixels, 30, 80, BACKGROUNDS_VR) == 0  # half transparent
    assert at(pixels, 30 - MOVING_MARGIN, 80 - MOVING_MARGIN, BACKGROUNDS_VR) == 0


def test_the_static_render_is_cached_per_extraction_and_read_back(
    root: Path, tmp_path: Path, mocker: MockerFixture
) -> None:
    render = static_render(root, tmp_path, LAYERS)
    first = render.pixels()

    assert render.path == tmp_path / render.build / f"{LAYERS}.png"
    assert render.path.is_file()
    draw = mocker.patch("maple.model.world.static_render.draw_static")
    again = render.pixels()

    draw.assert_not_called()
    assert np.array_equal(again, first)


def test_a_missing_render_is_drawn_again(root: Path, tmp_path: Path) -> None:
    render = static_render(root, tmp_path, LAYERS)
    first = render.pixels()
    render.path.unlink()

    assert np.array_equal(render.pixels(), first)
    assert render.path.is_file()
