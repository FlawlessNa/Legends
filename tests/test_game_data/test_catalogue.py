"""
The catalogue, built from the raw layer of a synthetic client's extraction.

`write_map_client` writes a client of five maps, every value invented:

- `100`, "Victoria Road: Henesys": a town with VR bounds and a minimap, its own
  footholds, a rope, two portals, a mob and an NPC; on layer 0, two tiles
  (one carrying a foothold), an animated object carrying a foothold, a flipped
  object carrying two, and a ladder object; and three backgrounds, one
  animated and one with no image.
- `101`, "Victoria Road: Henesys Hunting Ground".
- `200` and `201`, both "Mushroom Town", on different streets.
- `300`, which `String/Map.img` doesn't name, has no VR bounds and no minimap.

Its strings also name the mobs and skills of `test_catalogue_mobs_skills`,
whose client adds them to this one.
"""

import dataclasses
import json
import shutil
import sqlite3
import zlib
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture

from game_data.catalogue import (
    CATALOGUE,
    SCHEMA_VERSION,
    Background,
    Bounds,
    Catalogue,
    CatalogueError,
    Foothold,
    LayerFrame,
    Minimap,
    Portal,
    Ref,
    Rope,
    Spawn,
    build,
    build_catalogue,
)
from game_data.extraction import Manifest, extract
from tests.test_game_data import wz_writer as w

HENESYS = 100
NO_MAP = 999999999


def _pixels(red: int) -> bytes:
    return zlib.compress(bytes([0, 0, red, 255]))


def canvas(name: str, red: int, *children: w.Property) -> w.Canvas:
    """A 1x1 canvas, its colour set by `red` so each image is its own."""
    return w.Canvas(name, 1, 1, _pixels(red), format=2, children=children)


def foothold_tree(*footholds: tuple[int, int, int, int, int, int, int]) -> w.Prop:
    """`foothold/0/1/<id>`, from `(id, x1, y1, x2, y2, prev, next)`."""
    return w.Prop(
        "foothold",
        [
            w.Prop(
                "0",
                [
                    w.Prop(
                        "1",
                        [
                            w.Prop(
                                str(fh_id),
                                [
                                    w.Int(key, value)
                                    for key, value in zip(
                                        ("x1", "y1", "x2", "y2", "prev", "next"),
                                        rest,
                                        strict=True,
                                    )
                                ],
                            )
                            for fh_id, *rest in footholds
                        ],
                    )
                ],
            )
        ],
    )


def info(*extra: w.Property, vr: tuple[int, int, int, int] | None) -> w.Prop:
    bounds = (
        []
        if vr is None
        else [
            w.Int(key, value)
            for key, value in zip(
                ("VRLeft", "VRTop", "VRRight", "VRBottom"), vr, strict=True
            )
        ]
    )
    return w.Prop("info", [w.Int("version", 10), *extra, *bounds])


def _ints(**values: int) -> list[w.Property]:
    return [w.Int(key, value) for key, value in values.items()]


def henesys() -> list[w.Property]:
    return [
        info(
            w.Int("town", 1),
            w.String("bgm", "Bgm00/Test"),
            w.Int("returnMap", HENESYS),
            w.Int("fieldLimit", 4),
            vr=(-100, -200, 900, 300),
        ),
        w.Prop(
            "miniMap",
            [
                canvas("canvas", 1),
                *_ints(width=1000, height=500, centerX=100, centerY=200, mag=4),
            ],
        ),
        foothold_tree((1, 0, 0, 90, 0, 0, 2), (2, 90, 0, 180, 10, 1, 0)),
        w.Prop(
            "ladderRope",
            [w.Prop("1", _ints(l=1, uf=1, x=50, y1=-100, y2=0, page=0))],
        ),
        w.Prop(
            "portal",
            [
                w.Prop(
                    "0",
                    [
                        w.String("pn", "sp"),
                        *_ints(pt=0, x=5, y=-5, tm=NO_MAP),
                        w.String("tn", ""),
                    ],
                ),
                w.Prop(
                    "1",
                    [
                        w.String("pn", "east00"),
                        *_ints(pt=2, x=850, y=0, tm=101),
                        w.String("tn", "west00"),
                    ],
                ),
            ],
        ),
        w.Prop(
            "life",
            [
                w.Prop(
                    "0",
                    [
                        w.String("type", "m"),
                        w.String("id", "0100100"),
                        *_ints(x=10, y=-5, cy=0, fh=1, rx0=-40, rx1=60, mobTime=30),
                    ],
                ),
                w.Prop(
                    "1",
                    [
                        w.String("type", "n"),
                        w.String("id", "1012000"),
                        *_ints(x=120, y=0, cy=5, fh=2, rx0=100, rx1=140, f=1, hide=1),
                    ],
                ),
            ],
        ),
        w.Prop(
            "0",
            [
                w.Prop("info", [w.String("tS", "tile_test")]),
                w.Prop(
                    "tile",
                    [
                        w.Prop(
                            "0", [w.String("u", "bsc"), *_ints(no=0, x=0, y=0, zM=1)]
                        ),
                        w.Prop(
                            "1", [w.String("u", "enH0"), *_ints(no=0, x=90, y=0, zM=2)]
                        ),
                    ],
                ),
                w.Prop(
                    "obj",
                    [
                        _obj("0", "house", "a", "0", x=200, y=0, z=3, zM=0, f=0),
                        _obj("1", "house", "a", "1", x=400, y=10, z=1, zM=0, f=1),
                        _obj("2", "connect", "ladder", "0", x=600, y=-50, z=0, zM=0),
                    ],
                ),
            ],
        ),
        w.Prop(
            "back",
            [
                w.Prop(
                    "0",
                    [
                        w.String("bS", "back_test"),
                        *_ints(no=0, x=1, y=2, rx=-50, ry=-60, type=3, cx=10, cy=20),
                        *_ints(a=255, front=0, ani=0, f=0),
                    ],
                ),
                w.Prop(
                    "1",
                    [
                        w.String("bS", "back_test"),
                        w.String("no", "0"),
                        *_ints(x=3, y=4, rx=0, ry=0, type=0, cx=0, cy=0),
                        *_ints(a=128, front=1, ani=1, f=1),
                    ],
                ),
                w.Prop(
                    "2",
                    [
                        w.String("bS", ""),
                        *_ints(no=0, x=0, y=0, rx=0, ry=0, type=0, cx=0, cy=0),
                        *_ints(a=255, front=0, ani=0),
                    ],
                ),
            ],
        ),
    ]


def _obj(name: str, os_: str, *path: str, **values: int) -> w.Prop:
    return w.Prop(
        name,
        [
            w.String("oS", "obj_test"),
            *(w.String(f"l{n}", step) for n, step in enumerate((os_, *path))),
            *_ints(**values),
        ],
    )


def small_map(
    *, vr: tuple[int, int, int, int] | None = (0, 0, 100, 100)
) -> list[w.Property]:
    return [
        info(vr=vr),
        foothold_tree((1, -10, 5, 50, 25, 0, 2), (2, 50, 25, 60, -30, 1, 0)),
    ]


def obj_assets() -> list[w.Property]:
    return [
        w.Prop(
            "house",
            [
                w.Prop(
                    "a",
                    [
                        w.Prop(
                            "0",
                            [
                                canvas(
                                    "0",
                                    10,
                                    w.Vector("origin", 5, 6),
                                    w.Int("z", 0),
                                    w.Int("delay", 120),
                                    w.Convex("foothold", [(-10, 0), (0, -5), (10, 0)]),
                                ),
                                canvas(
                                    "1",
                                    11,
                                    w.Vector("origin", 7, 8),
                                    w.Int("delay", 90),
                                ),
                                w.Uol("2", "0"),
                            ],
                        ),
                        w.Prop(
                            "1",
                            [
                                canvas(
                                    "0",
                                    12,
                                    w.Vector("origin", 1, 1),
                                    w.Prop(
                                        "foothold",
                                        [
                                            w.Convex("0", [(5, 0), (20, 0)]),
                                            w.Convex("1", [(-5, -10), (-15, -10)]),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ],
                )
            ],
        ),
        w.Prop(
            "connect",
            [
                w.Prop(
                    "ladder",
                    [
                        w.Prop(
                            "0",
                            [
                                canvas(
                                    "0",
                                    13,
                                    w.Vector("origin", 3, 3),
                                    w.Convex("ladder", [(2, -40), (2, 0)]),
                                )
                            ],
                        )
                    ],
                )
            ],
        ),
    ]


def tile_assets() -> list[w.Property]:
    return [
        w.Prop("bsc", [canvas("0", 20, w.Vector("origin", 0, 0), w.Int("z", 0))]),
        w.Prop(
            "enH0",
            [
                canvas(
                    "0",
                    21,
                    w.Vector("origin", 0, 25),
                    w.Int("z", -3),
                    w.Convex("foothold", [(0, -25), (90, -25)]),
                )
            ],
        ),
    ]


def back_assets() -> list[w.Property]:
    return [
        w.Prop("back", [canvas("0", 30, w.Vector("origin", 64, 32))]),
        w.Prop(
            "ani",
            [
                w.Prop(
                    "0",
                    [
                        canvas("0", 31, w.Vector("origin", 1, 2), w.Int("delay", 150)),
                        canvas("1", 32, w.Vector("origin", 3, 4), w.Int("delay", 150)),
                    ],
                )
            ],
        ),
    ]


def strings() -> list[w.Img]:
    def map_entry(map_id: str, street: str, name: str, *more: w.Property) -> w.Prop:
        return w.Prop(
            map_id, [w.String("streetName", street), w.String("mapName", name), *more]
        )

    return [
        w.Img(
            "Map.img",
            [
                w.Prop(
                    "victoria",
                    [
                        map_entry(
                            "000000100",
                            "Victoria Road",
                            "Henesys",
                            w.String("mapDesc", "A town."),
                        ),
                        map_entry(
                            "000000101", "Victoria Road", "Henesys Hunting Ground"
                        ),
                    ],
                ),
                w.Prop(
                    "maple",
                    [
                        map_entry("000000200", "Maple Road", "Mushroom Town"),
                        map_entry("000000201", "Rainbow Street", "Mushroom Town"),
                    ],
                ),
            ],
        ),
        w.Img(
            "Mob.img",
            [
                w.Prop("100100", [w.String("name", "Snail")]),
                w.Prop("100101", [w.String("name", "Blue Snail")]),
                w.Prop("130100", [w.String("name", "Stump")]),
            ],
        ),
        w.Img("Npc.img", [w.Prop("1012000", [w.String("name", "Regular Cab")])]),
        w.Img(
            "Skill.img",
            [
                w.Prop("200", [w.String("bookName", "Magician")]),
                w.Prop(
                    "2001002",
                    [w.String("name", "Energy Bolt"), w.String("desc", "A bolt.")],
                ),
                w.Prop(
                    "2001003",
                    [w.String("name", "Magic Claw"), w.String("desc", "Two claws.")],
                ),
                w.Prop("2100000", [w.String("name", "MP Eater")]),
                w.Prop("2200000", [w.String("name", "MP Eater")]),
            ],
        ),
    ]


def write_map_client(data: Path) -> Path:
    """The client described above, in `data`."""
    w.write_tree(
        data / "Map",
        stub=[w.Dir("Map"), w.Dir("Obj"), w.Dir("Tile"), w.Dir("Back")],
        parts=[
            [
                w.Img(
                    "Physics.img",
                    [w.Float("walkSpeed", 125.0), w.Double("gravityAcc", 2000.0)],
                ),
                w.Dir("Obj", [w.Img("obj_test.img", obj_assets())]),
                w.Dir("Tile", [w.Img("tile_test.img", tile_assets())]),
                w.Dir("Back", [w.Img("back_test.img", back_assets())]),
            ]
        ],
    )
    w.write_tree(data / "Map" / "Map", stub=[w.Dir("Map0")], ini=False)
    w.write_tree(
        data / "Map" / "Map" / "Map0",
        stub=[],
        parts=[
            [
                w.Img("000000100.img", henesys()),
                w.Img("000000101.img", small_map()),
                w.Img("000000200.img", small_map()),
                w.Img("000000201.img", small_map()),
                w.Img("000000300.img", small_map(vr=None)),
            ]
        ],
    )
    w.write_tree(data / "String", stub=[], parts=[strings()])
    return data


@pytest.fixture
def client(tmp_path: Path) -> Path:
    return write_map_client(tmp_path / "Data")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "store"


@pytest.fixture
def extracted(client: Path, root: Path) -> str:
    """The client extracted with its catalogue; the build id."""
    return extract(client, root, catalogue=build_catalogue).manifest.build


@pytest.fixture
def cat(extracted: str, root: Path) -> Iterator[Catalogue]:
    with Catalogue.open(extracted, root) as catalogue:
        yield catalogue


def rows(root: Path, build_id: str, sql: str) -> list[tuple[Any, ...]]:
    file = root / "extractions" / build_id / CATALOGUE
    with closing(sqlite3.connect(file)) as database:
        return database.execute(sql).fetchall()


# --- building it -------------------------------------------------------------


def test_extract_builds_the_catalogue_through_its_hook_and_records_its_version(
    extracted: str, root: Path
) -> None:
    folder = root / "extractions" / extracted

    assert (folder / CATALOGUE).is_file()
    assert Manifest.read(folder).catalogue_schema_version == SCHEMA_VERSION
    assert rows(root, extracted, "PRAGMA user_version") == [(SCHEMA_VERSION,)]


def test_the_catalogue_builds_from_the_raw_layer_with_no_client(
    client: Path, root: Path
) -> None:
    """Extracted without a catalogue, then the client is gone."""
    build_id = extract(client, root).manifest.build
    folder = root / "extractions" / build_id
    assert Manifest.read(folder).catalogue_schema_version is None
    shutil.rmtree(client)

    with Catalogue.latest(root) as cat:
        found = cat.map("Henesys")

    assert found.id == HENESYS
    assert Manifest.read(folder).catalogue_schema_version == SCHEMA_VERSION
    assert (folder / CATALOGUE).is_file()


def test_bumping_the_schema_version_rebuilds_the_catalogue_when_opened(
    extracted: str, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root / "extractions" / extracted
    with closing(sqlite3.connect(folder / CATALOGUE)) as database:
        database.execute("DELETE FROM maps")
        database.commit()
    monkeypatch.setattr(
        "game_data.catalogue.catalogue.SCHEMA_VERSION", SCHEMA_VERSION + 1
    )

    with Catalogue.open(extracted, root) as cat:
        found = cat.map(HENESYS)

    assert found.name == "Henesys"
    assert Manifest.read(folder).catalogue_schema_version == SCHEMA_VERSION + 1


def test_a_current_catalogue_opens_without_being_rebuilt(
    extracted: str, root: Path, mocker: MockerFixture
) -> None:
    rebuild = mocker.patch("game_data.catalogue.catalogue.build_from_raw")

    with Catalogue.open(extracted, root):
        pass

    rebuild.assert_not_called()


def test_a_store_with_no_extraction_has_no_catalogue(root: Path) -> None:
    with pytest.raises(CatalogueError, match="has no extraction"):
        Catalogue.latest(root)
    with pytest.raises(CatalogueError, match="has no extraction 0123"):
        Catalogue.open("0123", root)


def test_a_failed_build_leaves_the_existing_catalogue_untouched(
    extracted: str, root: Path
) -> None:
    folder = root / "extractions" / extracted
    before = (folder / CATALOGUE).read_bytes()
    with closing(sqlite3.connect(folder / "raw.sqlite")) as database:
        database.execute("DELETE FROM images WHERE path = 'Map/Obj/obj_test.img'")
        database.commit()

    with pytest.raises(CatalogueError) as raised:
        build(folder)

    assert str(raised.value) == (
        "image Map/Map/Map0/000000100.img, node 0/obj/0: it names "
        "Map/Obj/obj_test.img, which the raw layer doesn't have"
    )
    assert (folder / CATALOGUE).read_bytes() == before
    assert sorted(f.name for f in folder.iterdir()) == [
        CATALOGUE,
        "manifest.json",
        "raw.sqlite",
    ]


# --- the tables ----------------------------------------------------------------


def test_maps_hold_their_bounds_flags_and_minimap(cat: Catalogue) -> None:
    found = cat.map(HENESYS)

    assert (found.name, found.street) == ("Henesys", "Victoria Road")
    assert found.vr == Bounds(-100, -200, 900, 300)
    assert not found.vr_derived
    assert found.minimap == Minimap(100, 200, 4, 1000, 500)
    assert (found.town, found.swim, found.fly) == (True, False, False)
    assert found.field_limit == 4
    assert (found.bgm, found.return_map) == ("Bgm00/Test", HENESYS)


def test_a_map_without_vr_bounds_gets_its_footholds_extents_flagged(
    cat: Catalogue,
) -> None:
    found = cat.map(300)

    assert found.vr == Bounds(-10, -30, 60, 25)
    assert found.vr_derived
    assert found.minimap is None
    assert (found.name, found.street, found.bgm, found.return_map) == (
        None,
        None,
        None,
        None,
    )


def test_a_maps_own_footholds_keep_their_layer_group_and_links(
    cat: Catalogue,
) -> None:
    own = [f for f in cat.map(HENESYS).footholds if f.source == "map"]

    assert own == [
        Foothold("map", 0, 1, 1, 0, 0, 90, 0, 0, 2),
        Foothold("map", 0, 1, 2, 90, 0, 180, 10, 1, 0),
    ]


def test_object_footholds_are_one_row_per_segment_placed_and_flipped(
    cat: Catalogue,
) -> None:
    """
    Object 0 at (200, 0) draws a polyline of three points: two segments.
    Object 1 at (400, 10), flipped, draws two polylines, mirrored about x 400.
    """
    found = [f for f in cat.map(HENESYS).footholds if f.source == "object"]

    assert [(f.x1, f.y1, f.x2, f.y2) for f in found] == [
        (190, 0, 200, -5),
        (200, -5, 210, 0),
        (395, 10, 380, 10),
        (405, 0, 415, 0),
    ]
    assert [f.id for f in found] == [0, 1, 2, 3]
    assert {(f.layer, f.group, f.prev, f.next) for f in found} == {
        (None, None, None, None)
    }


def test_tile_footholds_are_placed_at_the_tile(cat: Catalogue) -> None:
    found = [f for f in cat.map(HENESYS).footholds if f.source == "tile"]

    assert found == [Foothold("tile", None, None, 0, 90, -25, 180, -25, None, None)]


def test_ropes_come_from_the_map_and_from_ladder_objects(cat: Catalogue) -> None:
    assert cat.map(HENESYS).ropes == (
        Rope("map", 1, 50, -100, 0, True, True, 0),
        Rope("object", 0, 602, -90, -50, None, None, None),
    )


def test_portals_with_no_target_say_so(cat: Catalogue) -> None:
    assert cat.map(HENESYS).portals == (
        Portal("sp", 0, 5, -5, None, None),
        Portal("east00", 2, 850, 0, 101, "west00"),
    )


def test_spawns_carry_their_names(cat: Catalogue) -> None:
    assert cat.map(HENESYS).spawns == (
        Spawn("mob", 100100, "Snail", 10, 0, 1, -40, 60, 30, False, False),
        Spawn("npc", 1012000, "Regular Cab", 120, 5, 2, 100, 140, None, True, True),
    )


def test_map_layers_keep_raw_positions_with_their_frames(cat: Catalogue) -> None:
    layers = cat.map_layers("Henesys")

    assert [(x.kind, x.layer, x.z, x.zm, x.x, x.y, x.flip) for x in layers] == [
        ("object", 0, 3, 0, 200, 0, False),
        ("object", 0, 1, 0, 400, 10, True),
        ("object", 0, 0, 0, 600, -50, False),
        ("tile", 0, 0, 1, 0, 0, False),
        ("tile", 0, -3, 2, 90, 0, False),
        ("back", None, 0, None, 1, 2, False),
        ("back", None, 1, None, 3, 4, True),
        ("back", None, 2, None, 0, 0, False),
    ]
    assert [x.asset for x in layers] == [
        "Map/Obj/obj_test.img/house/a/0",
        "Map/Obj/obj_test.img/house/a/1",
        "Map/Obj/obj_test.img/connect/ladder/0",
        "Map/Tile/tile_test.img/bsc/0",
        "Map/Tile/tile_test.img/enH0/0",
        "Map/Back/back_test.img/back/0",
        "Map/Back/back_test.img/ani/0",
        None,
    ]
    assert [len(x.frames) for x in layers] == [3, 1, 1, 1, 1, 1, 2, 0]
    assert [x.background for x in layers[5:]] == [
        Background(3, -50, -60, 10, 20, 255, False),
        Background(0, 0, 0, 0, 0, 128, True),
        Background(0, 0, 0, 0, 0, 255, False),
    ]
    assert {x.background for x in layers[:5]} == {None}


def test_an_animated_objects_frames_follow_their_links(cat: Catalogue) -> None:
    frames = cat.map_layers(HENESYS)[0].frames

    assert [(f.frame, f.origin_x, f.origin_y, f.delay) for f in frames] == [
        (0, 5, 6, 120),
        (1, 7, 8, 90),
        (2, 5, 6, 120),
    ]
    assert frames[0].image is not None
    assert frames[2].image == frames[0].image != frames[1].image


def test_the_layer_tables_hold_one_row_per_item_and_per_frame(
    extracted: str, root: Path
) -> None:
    (items,) = rows(root, extracted, "SELECT count(*) FROM map_layers")
    frames = rows(
        root,
        extracted,
        "SELECT item, frame_count, map_layers.origin_x, map_layers.origin_y, "
        "count(frame) "
        "FROM map_layers LEFT JOIN layer_frames USING (item) GROUP BY item",
    )

    assert items == (8,)
    assert [row[1] for row in frames] == [row[4] for row in frames]
    assert frames[0][2:4] == (5, 6)
    assert frames[-1][1:4] == (0, None, None)


def test_physics_is_every_value_of_physics_img(cat: Catalogue) -> None:
    assert cat.physics() == {"gravityAcc": 2000.0, "walkSpeed": 125.0}


def test_strings_hold_map_mob_npc_and_skill_names(extracted: str, root: Path) -> None:
    found = rows(root, extracted, "SELECT * FROM strings ORDER BY kind, id")

    assert found == [
        ("map", 100, "Henesys", "A town."),
        ("map", 101, "Henesys Hunting Ground", None),
        ("map", 200, "Mushroom Town", None),
        ("map", 201, "Mushroom Town", None),
        ("mob", 100100, "Snail", None),
        ("mob", 100101, "Blue Snail", None),
        ("mob", 130100, "Stump", None),
        ("npc", 1012000, "Regular Cab", None),
        ("skill", 2001002, "Energy Bolt", "A bolt."),
        ("skill", 2001003, "Magic Claw", "Two claws."),
        ("skill", 2100000, "MP Eater", None),
        ("skill", 2200000, "MP Eater", None),
    ]


# --- looking up --------------------------------------------------------------


@pytest.mark.parametrize(
    "wanted",
    [HENESYS, "100", "000000100", "Henesys", "  hEnEsYs ", "victoria road: henesys"],
)
def test_a_map_is_found_by_id_or_by_name_case_aside(
    cat: Catalogue, wanted: str | int
) -> None:
    assert cat.map(wanted) == cat.map(HENESYS)


def test_a_street_tells_two_maps_of_one_name_apart(cat: Catalogue) -> None:
    assert cat.map("Rainbow Street: Mushroom Town").id == 201


def test_an_ambiguous_name_lists_every_map_with_its_id(cat: Catalogue) -> None:
    with pytest.raises(LookupError) as raised:
        cat.map("mushroom town")

    assert str(raised.value.args[0]) == (
        "'mushroom town' names 2 maps: Maple Road: Mushroom Town (200), "
        "Rainbow Street: Mushroom Town (201). Ask for one by `street: map name` "
        "or by ID"
    )


def test_an_unknown_name_lists_the_closest_names(cat: Catalogue) -> None:
    with pytest.raises(LookupError) as raised:
        cat.map("Henesis")

    message = str(raised.value.args[0])
    assert message.startswith("no map is named 'Henesis'; the closest are: Henesys")
    assert len(message.split(": ", 1)[1].split(", ")) <= 5


def test_an_unknown_id_or_a_name_like_nothing_says_so(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="no map has the ID 404"):
        cat.map(404)
    with pytest.raises(LookupError, match=r"^no map is named 'zzzzzz'$"):
        cat.map("zzzzzz")


def test_search_lists_what_contains_the_text_with_ids(cat: Catalogue) -> None:
    assert cat.search("henesys") == [
        Ref("map", 100, "Victoria Road: Henesys"),
        Ref("map", 101, "Victoria Road: Henesys Hunting Ground"),
    ]
    assert cat.search("RAINBOW") == [Ref("map", 201, "Rainbow Street: Mushroom Town")]
    assert cat.search("300") == [Ref("map", 300, None)]


def test_lookups_return_frozen_dataclasses(cat: Catalogue) -> None:
    found = cat.map(HENESYS)
    layer = cat.map_layers(HENESYS)[0]

    for value in (found, found.vr, found.footholds[0], layer, layer.frames[0]):
        assert dataclasses.is_dataclass(value)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, 0)
    assert isinstance(layer.frames[0], LayerFrame)


# --- a raw layer the catalogue doesn't understand -----------------------------


def write_raw(folder: Path, trees: dict[str, Any]) -> Path:
    """An extraction folder with only a raw layer, holding `trees`."""
    folder.mkdir(parents=True)
    with closing(sqlite3.connect(folder / "raw.sqlite")) as database:
        database.execute("CREATE TABLE images (path TEXT, sha256 TEXT, tree TEXT)")
        database.executemany(
            "INSERT INTO images VALUES (?, '', ?)",
            [(path, json.dumps(tree)) for path, tree in trees.items()],
        )
        database.commit()
    return folder


def _map(**tree: object) -> dict[str, object]:
    vr = {"VRLeft": 0, "VRTop": 0, "VRRight": 1, "VRBottom": 1}
    return {"info": vr} | tree


@pytest.mark.parametrize(
    ("tree", "message"),
    [
        (
            {"info": {"VRLeft": 0}},
            "node info: it has some of the VR bounds but not all four",
        ),
        ({"info": {}}, "node info: it has no VR bounds, and no footholds to derive"),
        (
            _map(life={"0": {"type": "r", "id": "1"}}),
            "node life/0/type: a life type that isn't m or n",
        ),
        (
            _map(portal={"0": {"pn": "sp", "pt": "x", "tm": 1, "tn": ""}}),
            "node portal/0/pt: it is a string, not an integer",
        ),
        (
            _map(back={"0": {"bS": "b", "ani": 2}}),
            "node back/0/ani: a background of kind 2",
        ),
        (
            _map(**{"0": {"info": {}, "tile": {"0": {"u": "a", "no": 0}}}}),
            "node 0/tile/0: its layer's info has no tS",
        ),
        (
            _map(foothold={"0": {"x": {}}}),
            "node foothold/0/x: a child that isn't numbered",
        ),
    ],
)
def test_a_map_tree_out_of_shape_names_its_node(
    tmp_path: Path, tree: dict[str, Any], message: str
) -> None:
    folder = write_raw(tmp_path / "x", {"Map/Map/Map0/000000001.img": tree})

    with pytest.raises(CatalogueError) as raised:
        build(folder)

    assert str(raised.value).startswith(f"image Map/Map/Map0/000000001.img, {message}")
    assert not (folder / CATALOGUE).exists()


def test_a_raw_layer_with_no_maps_or_strings_builds_empty_tables(
    tmp_path: Path,
) -> None:
    folder = write_raw(tmp_path / "x", {"Etc/a.img": {}})

    build(folder)

    with closing(sqlite3.connect(folder / CATALOGUE)) as database:
        tables = [
            name
            for (name,) in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        counts = {
            table: database.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    assert len(counts) == 17
    assert set(counts.values()) == {0}


def test_two_maps_of_one_id_are_an_error(tmp_path: Path) -> None:
    folder = write_raw(
        tmp_path / "x",
        {
            "Map/Map/Map0/000000001.img": _map(),
            "Map/Map/Map1/000000001.img": _map(),
        },
    )

    with pytest.raises(CatalogueError, match="are both map 1"):
        build(folder)


# --- the documented schema ----------------------------------------------------

DOC = Path(__file__).resolve().parents[2] / "docs" / "agents" / "game-data.md"


def documented_tables() -> dict[str, list[str]]:
    """
    The tables and columns `docs/agents/game-data.md` lists under
    `### catalogue.sqlite`: each a `#### \\`table\\`` heading, then a table whose
    first column names each column.
    """
    text = DOC.read_text(encoding="utf-8")
    section = text.split("### `catalogue.sqlite`", 1)[1].split("\n### ", 1)[0]
    tables: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in section.splitlines():
        if line.startswith("#### `"):
            current = tables.setdefault(line.split("`")[1], [])
        elif current is not None and line.startswith("| `"):
            current.append(line.split("`")[1])
    return tables


def test_the_docs_list_every_catalogue_table_and_column(
    extracted: str, root: Path
) -> None:
    file = root / "extractions" / extracted / CATALOGUE
    with closing(sqlite3.connect(file)) as database:
        names = [
            name
            for (name,) in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY rowid"
            )
        ]
        schema = {
            name: [row[1] for row in database.execute(f"PRAGMA table_info({name})")]
            for name in names
        }

    assert documented_tables() == schema
