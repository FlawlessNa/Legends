"""
`WorldMap` on the real client's maps, from the latest extraction in the
store (`python -m game_data extract`). Marked `client_files`; run with
`pytest -m client_files`.

The static render is drawn into a temporary folder, never the real cache.
"""

from pathlib import Path

import pytest

from game_data.catalogue import Catalogue
from game_data.config import STORE
from maple.model.world import WorldMap, is_wall

pytestmark = pytest.mark.client_files

MAPS = ("Dungeon: Damp Forest", "Victoria Road: Ellinia")


@pytest.fixture(scope="module", params=MAPS)
def name(request: pytest.FixtureRequest) -> str:
    return request.param


def test_every_non_wall_foothold_lies_on_exactly_one_platform(name: str) -> None:
    with Catalogue.latest(STORE) as cat:
        own = [f for f in cat.map(name).footholds if f.source == "map"]
    world = WorldMap.load(name)

    on_platforms = [f for p in world.platforms for f in p.footholds]
    assert sorted(f.id for f in on_platforms) == sorted(
        f.id for f in own if not is_wall(f)
    )
    assert {f.id for f in world.walls} == {f.id for f in own if is_wall(f)}
    assert not any(is_wall(f) for f in on_platforms)
    assert all(len({f.layer for f in p.footholds}) == 1 for p in world.platforms)


def test_ropes_are_the_maps_own_and_keep_their_top_flags(name: str) -> None:
    with Catalogue.latest(STORE) as cat:
        ropes = cat.map(name).ropes
    world = WorldMap.load(name)

    assert world.ropes == tuple(r for r in ropes if r.source == "map")
    assert world.ropes
    assert all(
        r.usable_from_foothold is not None and r.ladder is not None for r in world.ropes
    )


def test_damp_forest_has_walls_and_the_minimap_transform() -> None:
    world = WorldMap.load("Dungeon: Damp Forest")

    assert world.walls
    flags = {r.usable_from_foothold for r in world.ropes}
    assert flags == {True, False}
    assert world.minimap is not None
    assert world.minimap.scale == 16


def test_the_static_render_is_the_vr_bounds(name: str, tmp_path: Path) -> None:
    world = WorldMap.load(name, cache=tmp_path)
    assert world.static_render is not None

    pixels = world.static_render.pixels()

    bounds = world.bounds
    assert pixels.shape == (bounds.bottom - bounds.top, bounds.right - bounds.left, 4)
    assert (pixels[..., 3] > 0).mean() > 0.2
    assert world.static_render.path.is_relative_to(tmp_path)
