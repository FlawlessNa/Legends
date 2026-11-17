"""
`maple.model.world.hunting_area`: the stretches a rectangle holds on a Fixture
map written here, the cells they are cut into, and the saved file, written
under a temporary folder.
"""

from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from game_data.catalogue import Bounds, Foothold, MapData
from maple.model.world import (
    CELL,
    EmptyHuntingArea,
    HuntingArea,
    Platform,
    Stretch,
    UnknownHuntingArea,
    WorldMap,
    cells,
)
from maple.model.world.hunting_area import (
    HUNTING_AREAS,
    load_area,
    save_area,
    saved_areas,
)


def chain(first_id: int, *points: tuple[int, int]) -> tuple[Foothold, ...]:
    """One Platform through `points`, its footholds linked by prev/next."""
    last = first_id + len(points) - 2
    return tuple(
        Foothold(
            "map",
            0,
            1,
            fid,
            x1,
            y1,
            x2,
            y2,
            fid - 1 if fid > first_id else 0,
            fid + 1 if fid < last else 0,
        )
        for fid, ((x1, y1), (x2, y2)) in enumerate(pairwise(points), start=first_id)
    )


FLAT = chain(1, (0, 0), (1000, 0))
"""A flat Platform at y 0, from x 0 to 1000."""

PEAK = chain(10, (2000, 0), (2200, -200), (2400, 0))
"""A Platform up a slope and down again: at y -100 at x 2100 and 2300."""

HIGH = chain(20, (0, -1000), (1000, -1000))
"""A flat Platform far above `FLAT`."""


def fixture_map(**changes: object) -> WorldMap:
    data = MapData(
        id=104010001,
        name="Somewhere",
        street="Test Road",
        vr=Bounds(-500, -1500, 3000, 500),
        vr_derived=False,
        minimap=None,
        town=False,
        swim=False,
        fly=False,
        field_limit=0,
        bgm=None,
        return_map=None,
        footholds=FLAT + PEAK + HIGH,
        ropes=(),
        portals=(),
        spawns=(),
    )
    return WorldMap.from_map_data(replace(data, **changes))


def platform(world: WorldMap, first_id: int) -> Platform:
    (found,) = [p for p in world.platforms if p.footholds[0].id == first_id]
    return found


# --- stretches -----------------------------------------------------------------


def test_a_platform_crossing_the_rectangles_sides_gives_the_part_inside() -> None:
    world = fixture_map()

    found = HuntingArea(200, -100, 600, 50).stretches(world)

    assert found == (Stretch(platform(world, 1), 200, 600),)
    assert found[0].y_at(400) == 0
    assert found[0].y_at(700) is None


def test_a_sloped_platform_gives_each_part_whose_height_is_inside() -> None:
    """The peak rises above the top at x 2100 and comes back under it at 2300."""
    world = fixture_map()

    found = HuntingArea(1900, -100, 2500, 50).stretches(world)

    peak = platform(world, 10)
    assert found == (Stretch(peak, 2000, 2100), Stretch(peak, 2300, 2400))
    assert found[0].y_at(2050) == -50


def test_the_edges_are_inside_the_rectangle() -> None:
    world = fixture_map()

    found = HuntingArea(1000, -1000, 1200, 0).stretches(world)

    assert found == (
        Stretch(platform(world, 1), 1000, 1000),
        Stretch(platform(world, 20), 1000, 1000),
    )


def test_a_platform_outside_gives_nothing_and_an_empty_rectangle_no_error() -> None:
    world = fixture_map()

    assert HuntingArea(200, -500, 600, -100).stretches(world) == ()
    assert HuntingArea(5000, -100, 6000, 50).stretches(world) == ()


def test_among_keeps_to_the_platforms_given() -> None:
    world = fixture_map()
    everything = HuntingArea(0, -1000, 1000, 0)

    found = everything.stretches(world, among=[platform(world, 20)])

    assert found == (Stretch(platform(world, 20), 0, 1000),)
    assert len(everything.stretches(world)) == 2


# --- require_stretches ---------------------------------------------------------


def test_require_stretches_gives_the_stretches_when_there_are_some() -> None:
    world = fixture_map()
    area = HuntingArea(200, -100, 600, 50)

    assert area.require_stretches(world) == area.stretches(world)


def test_require_stretches_refuses_a_rectangle_that_holds_none() -> None:
    area = HuntingArea(5000, -120, 6000, 55)

    with pytest.raises(EmptyHuntingArea) as raised:
        area.require_stretches(fixture_map())

    assert issubclass(EmptyHuntingArea, ValueError)
    message = str(raised.value)
    for named in ("104010001", "5000", "-120", "6000", "55"):
        assert named in message


def test_building_a_hunting_area_never_raises() -> None:
    """It knows no map: even an inverted rectangle is built, and holds nothing."""
    area = HuntingArea(600, 50, 200, -100)

    assert area.stretches(fixture_map()) == ()


# --- cells ---------------------------------------------------------------------


@pytest.mark.parametrize("width", [0, 1, 149, 150, 151, 300, 301, 1000])
def test_cells_cut_a_stretch_into_pieces_of_at_most_cell_that_cover_it(
    width: int,
) -> None:
    world = fixture_map()
    stretch = Stretch(platform(world, 1), 0, width)

    pieces = cells([stretch])

    assert CELL == 150
    assert all(p.right - p.left <= CELL for p in pieces)
    assert all(p.platform is stretch.platform for p in pieces)
    assert pieces[0].left == stretch.left
    assert pieces[-1].right == stretch.right
    assert all(a.right == b.left for a, b in pairwise(pieces))


def test_cells_cut_every_stretch_in_order() -> None:
    world = fixture_map()
    stretches = HuntingArea(1900, -100, 2500, 50).stretches(world) + HuntingArea(
        0, -100, 400, 50
    ).stretches(world)

    pieces = cells(stretches)

    assert [(p.left, p.right) for p in pieces] == [
        (2000, 2100),
        (2300, 2400),
        (0, 400 / 3),
        (400 / 3, 800 / 3),
        (800 / 3, 400),
    ]


# --- the saved file ------------------------------------------------------------


def test_a_saved_area_loads_equal(tmp_path: Path) -> None:
    world = fixture_map()
    area = HuntingArea(1210, -340, 2180, 215, name="right_corner")

    written = save_area(world, area, tmp_path)

    assert written == tmp_path / "104010001.json"
    assert load_area(world.id, "right_corner", tmp_path) == area


def test_the_file_has_the_specs_layout_with_areas_sorted_by_name(
    tmp_path: Path,
) -> None:
    world = fixture_map()
    save_area(world, HuntingArea(1210, -340, 2180, 215, name="right_corner"), tmp_path)
    save_area(world, HuntingArea(-10, -20, 30, 40, name="left"), tmp_path)

    text = (tmp_path / "104010001.json").read_bytes().decode("utf-8")

    assert text == (
        "{\n"
        '  "map": "Test Road: Somewhere",\n'
        '  "areas": {\n'
        '    "left": {"left": -10, "top": -20, "right": 30, "bottom": 40},\n'
        '    "right_corner": {"left": 1210, "top": -340, "right": 2180, "bottom": 215}\n'
        "  }\n"
        "}\n"
    )


@pytest.mark.parametrize(
    ("name", "street", "label"),
    [("Somewhere", None, "Somewhere"), (None, "Test Road", ""), (None, None, "")],
)
def test_the_map_field_is_the_name_alone_with_no_street_or_else_empty(
    tmp_path: Path, name: str | None, street: str | None, label: str
) -> None:
    world = fixture_map(name=name, street=street)
    save_area(world, HuntingArea(0, 0, 1, 1, name="a"), tmp_path)

    text = (tmp_path / "104010001.json").read_text(encoding="utf-8")

    assert f'  "map": "{label}",\n' in text


def test_saving_the_same_areas_twice_gives_the_same_bytes(tmp_path: Path) -> None:
    world = fixture_map()
    a = HuntingArea(0, -100, 500, 50, name="a")
    b = HuntingArea(600, -100, 900, 50, name="b")
    save_area(world, a, tmp_path / "one")
    save_area(world, b, tmp_path / "one")
    first = (tmp_path / "one" / "104010001.json").read_bytes()

    save_area(world, b, tmp_path / "two")
    save_area(world, a, tmp_path / "two")
    save_area(world, a, tmp_path / "one")

    assert (tmp_path / "two" / "104010001.json").read_bytes() == first
    assert (tmp_path / "one" / "104010001.json").read_bytes() == first
    assert sorted(p.name for p in (tmp_path / "one").iterdir()) == ["104010001.json"]


def test_saving_under_an_existing_name_replaces_that_area(tmp_path: Path) -> None:
    world = fixture_map()
    save_area(world, HuntingArea(0, -100, 500, 50, name="spot"), tmp_path)
    save_area(world, HuntingArea(9, 9, 99, 99, name="other"), tmp_path)

    save_area(world, HuntingArea(600, -100, 900, 50, name="spot"), tmp_path)

    assert saved_areas(world.id, tmp_path) == {
        "other": HuntingArea(9, 9, 99, 99, name="other"),
        "spot": HuntingArea(600, -100, 900, 50, name="spot"),
    }


def test_loading_a_name_the_file_lacks_lists_the_names_there_are(
    tmp_path: Path,
) -> None:
    world = fixture_map()
    save_area(world, HuntingArea(0, -100, 500, 50, name="west"), tmp_path)
    save_area(world, HuntingArea(600, -100, 900, 50, name="east"), tmp_path)

    with pytest.raises(UnknownHuntingArea) as raised:
        load_area(world.id, "north", tmp_path)

    assert issubclass(UnknownHuntingArea, LookupError)
    assert raised.value.names == ("east", "west")
    assert "east, west" in str(raised.value)
    assert "north" in str(raised.value)


def test_loading_from_a_missing_file_raises_unknown_hunting_area(
    tmp_path: Path,
) -> None:
    with pytest.raises(UnknownHuntingArea) as raised:
        load_area(104010001, "west", tmp_path)

    assert raised.value.names == ()
    assert saved_areas(104010001, tmp_path) == {}


@pytest.mark.parametrize(
    "name",
    [None, "", "a" * 25, "Right", "right-corner", "two words", "café", "a\n"],
)
def test_a_name_outside_the_rule_is_refused_on_save(
    tmp_path: Path, name: str | None
) -> None:
    area = HuntingArea(0, -100, 500, 50, name=name)

    with pytest.raises(ValueError, match="1 to 24 characters"):
        save_area(fixture_map(), area, tmp_path)

    assert not (tmp_path / "104010001.json").exists()


@pytest.mark.parametrize("name", ["a", "a" * 24, "spot_2", "0"])
def test_a_name_inside_the_rule_is_saved(tmp_path: Path, name: str) -> None:
    area = HuntingArea(0, -100, 500, 50, name=name)

    save_area(fixture_map(), area, tmp_path)

    assert load_area(104010001, name, tmp_path) == area


def test_saved_areas_default_to_the_tracked_configs_folder() -> None:
    assert HUNTING_AREAS == Path(__file__).resolve().parents[2] / "configs" / (
        "hunting_areas"
    )
