"""
`game_data.render`: map screens drawn from a synthetic client's catalogue and
image store.

`write_render_client` writes a client of two maps, every value invented, whose
images are small blocks of plain colours, so that a pixel tells which item
drew it:

- `100`, "Test Road: Layers", VR `(-100, -50)` to `(300, 150)`. On layer 0:
  two overlapping tiles, the later in the map with the lower `z`; an object
  and the same object flipped; an object with a high `z` under a tile; and an
  animated object of two frames. On layer 1, an object over a layer-0 tile.
  Its own foothold, a rope and a portal; a foothold on an object and one on a
  tile; a Snail, the same Snail flipped, and an NPC.
- `101`, "Test Road: Backgrounds", VR `(0, 0)` to `(200, 100)`: backgrounds
  with `rx` of -100, 0 and -50, one that tiles across, one that tiles down,
  one half transparent, one flipped, and one in front of an object.

The camera is centred on the map, so for `101` its centre is `(100, 50)`
whatever the viewport.
"""

import zlib
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest

from game_data.archive import Pixels
from game_data.catalogue import (
    Background,
    Bounds,
    Catalogue,
    MapLayer,
    build_catalogue,
)
from game_data.cli import main
from game_data.extraction import extract
from game_data.render import (
    STORED_AT_RX,
    Camera,
    RenderError,
    placement,
    render_map,
    render_path,
    write_png,
)
from game_data.render.screen import FOOTHOLD, HITBOX, NO_SPRITE, PORTAL, ROPE
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_catalogue import foothold_tree
from tests.test_game_data.test_catalogue_mobs_skills import mob_info

type Rgba = tuple[int, int, int, int]

RED: Rgba = (255, 0, 0, 255)
GREEN: Rgba = (0, 255, 0, 255)
BLUE: Rgba = (0, 0, 255, 255)
YELLOW: Rgba = (255, 255, 0, 255)
WHITE: Rgba = (255, 255, 255, 255)
NOTHING: Rgba = (0, 0, 0, 0)

LAYERS = 100
BACKGROUNDS = 101
LAYERS_VR = (-100, -50, 300, 150)
BACKGROUNDS_VR = (0, 0, 200, 100)


def image(name: str, rows: list[list[Rgba]], *children: w.Property) -> w.Canvas:
    """A canvas of these pixels, row by row, stored as BGRA8888."""
    data = bytes(
        channel for row in rows for r, g, b, a in row for channel in (b, g, r, a)
    )
    return w.Canvas(
        name,
        len(rows[0]),
        len(rows),
        zlib.compress(data),
        format=2,
        children=children,
    )


def solid(
    name: str, width: int, height: int, colour: Rgba, *children: w.Property
) -> w.Canvas:
    return image(name, [[colour] * width for _ in range(height)], *children)


def origin(x: int, y: int) -> w.Vector:
    return w.Vector("origin", x, y)


def _ints(**values: int) -> list[w.Property]:
    return [w.Int(key, value) for key, value in values.items()]


def _numbered(name: str, *children: list[w.Property]) -> w.Prop:
    return w.Prop(name, [w.Prop(str(n), list(c)) for n, c in enumerate(children)])


def _info(vr: tuple[int, int, int, int]) -> w.Prop:
    keys = ("VRLeft", "VRTop", "VRRight", "VRBottom")
    return w.Prop("info", [w.Int(key, value) for key, value in zip(keys, vr)])


def _obj(path: str, **values: int) -> list[w.Property]:
    l0, l1, l2 = path.split("/")
    return [
        w.String("oS", "otest"),
        w.String("l0", l0),
        w.String("l1", l1),
        w.String("l2", l2),
        *_ints(**{"z": 0, "zM": 0, "f": 0, **values}),
    ]


def _tile(u: str, no: int, x: int, y: int) -> list[w.Property]:
    return [w.String("u", u), *_ints(no=no, x=x, y=y, zM=0)]


def _back(no: int, **values: int) -> list[w.Property]:
    defaults = {
        "x": 0,
        "y": 0,
        "rx": -100,
        "ry": -100,
        "type": 0,
        "cx": 0,
        "cy": 0,
        "a": 255,
    }
    return [
        w.String("bS", "btest"),
        *_ints(**{**defaults, "no": no, "front": 0, "ani": 0, "f": 0, **values}),
    ]


def _life(kind: str, life_id: str, **values: int) -> list[w.Property]:
    defaults = {"y": 0, "fh": 1, "rx0": 0, "rx1": 0, "f": 0}
    return [
        w.String("type", kind),
        w.String("id", life_id),
        *_ints(**defaults | values),
    ]


def layers_map() -> list[w.Property]:
    return [
        _info(LAYERS_VR),
        foothold_tree((1, 140, 60, 260, 60, 0, 0)),
        _numbered("ladderRope", _ints(l=0, uf=1, x=270, y1=0, y2=40, page=0)),
        _numbered(
            "portal",
            [
                w.String("pn", "sp"),
                *_ints(pt=0, x=280, y=100, tm=999999999),
                w.String("tn", ""),
            ],
        ),
        _numbered(
            "life",
            _life("m", "0100100", x=150, cy=60),
            _life("m", "0100100", x=200, cy=60, f=1),
            _life("n", "1012000", x=130, cy=100),
        ),
        w.Prop(
            "0",
            [
                w.Prop("info", [w.String("tS", "ttest")]),
                _numbered("tile", _tile("bsc", 0, 0, 0), _tile("bsc", 1, 2, 0)),
                _numbered(
                    "obj",
                    _obj("house/a/0", x=50, y=20, z=1),
                    _obj("house/a/0", x=80, y=20, z=1, f=1),
                    _obj("box/a/0", x=4, y=1, z=9),
                    _obj("anim/a/0", x=120, y=0),
                ),
            ],
        ),
        w.Prop(
            "1",
            [
                w.Prop("info", []),
                _numbered("obj", _obj("dot/a/0", x=5, y=0)),
            ],
        ),
    ]


def backgrounds_map() -> list[w.Property]:
    return [
        _info(BACKGROUNDS_VR),
        w.Prop(
            "0",
            [
                w.Prop("info", []),
                _numbered(
                    "obj",
                    _obj("dot/a/0", x=10, y=10),
                    _obj("box/a/0", x=150, y=50),
                ),
            ],
        ),
        _numbered(
            "back",
            _back(0, x=10, y=10),
            _back(1, x=10, y=10, rx=0, ry=0),
            _back(2, x=10, y=10, rx=-50, ry=-50),
            _back(3, x=5, y=90, type=1, cx=50),
            _back(4, x=190, y=3, type=2),
            _back(5, x=30, y=80, a=128),
            _back(6, x=70, y=80, f=1),
            _back(7, x=150, y=50, front=1),
        ),
    ]


def object_assets() -> list[w.Property]:
    def asset(path: str, *frames: w.Property) -> w.Prop:
        l0, l1, l2 = path.split("/")
        return w.Prop(l0, [w.Prop(l1, [w.Prop(l2, list(frames))])])

    return [
        asset(
            "house/a/0",
            image(
                "0",
                [[BLUE, WHITE, WHITE], [BLUE, WHITE, WHITE]],
                origin(1, 2),
                w.Convex("foothold", [(-1, 0), (1, 0)]),
            ),
        ),
        asset("box/a/0", solid("0", 2, 2, YELLOW, origin(0, 0))),
        asset("dot/a/0", solid("0", 1, 1, YELLOW, origin(0, 0))),
        asset(
            "anim/a/0",
            solid("0", 1, 1, RED, origin(0, 0), w.Int("delay", 100)),
            solid("1", 1, 1, BLUE, origin(0, 1), w.Int("delay", 100)),
        ),
    ]


def tile_assets() -> list[w.Property]:
    return [
        w.Prop(
            "bsc",
            [
                solid("0", 4, 2, RED, origin(1, 1), w.Int("z", 0)),
                solid(
                    "1",
                    4,
                    2,
                    GREEN,
                    origin(0, 0),
                    w.Int("z", -1),
                    w.Convex("foothold", [(0, 5), (3, 5)]),
                ),
            ],
        )
    ]


def back_assets() -> list[w.Property]:
    return [
        w.Prop(
            "back",
            [
                solid("0", 3, 3, RED, origin(0, 0)),
                solid("1", 2, 2, GREEN, origin(0, 0)),
                solid("2", 2, 2, BLUE, origin(0, 0)),
                solid("3", 2, 1, YELLOW, origin(0, 0)),
                solid("4", 1, 10, WHITE, origin(0, 0)),
                solid("5", 1, 1, RED, origin(0, 0)),
                image("6", [[RED, GREEN]], origin(0, 0)),
                solid("7", 2, 2, BLUE, origin(0, 0)),
            ],
        )
    ]


def snail() -> w.Img:
    """A Snail whose stand frame is 4x3, blue in its left column."""
    rows = [[BLUE, RED, RED, RED] for _ in range(3)]
    return w.Img(
        "Mob/0100100.img",
        [
            mob_info(level=1),
            w.Prop(
                "stand",
                [
                    image(
                        "0",
                        rows,
                        origin(1, 3),
                        w.Vector("lt", -1, -3),
                        w.Vector("rb", 3, 0),
                    )
                ],
            ),
        ],
    )


def strings() -> list[w.Img]:
    def entry(map_id: str, name: str) -> w.Prop:
        return w.Prop(
            map_id, [w.String("streetName", "Test Road"), w.String("mapName", name)]
        )

    return [
        w.Img(
            "Map.img",
            [
                w.Prop(
                    "test",
                    [entry("000000100", "Layers"), entry("000000101", "Backgrounds")],
                )
            ],
        ),
        w.Img("Mob.img", [w.Prop("100100", [w.String("name", "Snail")])]),
        w.Img("Npc.img", [w.Prop("1012000", [w.String("name", "Regular Cab")])]),
    ]


def write_render_client(data: Path) -> Path:
    """The client described above, in `data`."""
    w.write_tree(
        data / "Map",
        stub=[w.Dir("Map"), w.Dir("Obj"), w.Dir("Tile"), w.Dir("Back")],
        parts=[
            [
                w.Img("Physics.img", [w.Float("walkSpeed", 125.0)]),
                w.Dir("Obj", [w.Img("otest.img", object_assets())]),
                w.Dir("Tile", [w.Img("ttest.img", tile_assets())]),
                w.Dir("Back", [w.Img("btest.img", back_assets())]),
            ]
        ],
    )
    w.write_tree(data / "Map" / "Map", stub=[w.Dir("Map0")], ini=False)
    w.write_tree(
        data / "Map" / "Map" / "Map0",
        stub=[],
        parts=[
            [
                w.Img("000000100.img", layers_map()),
                w.Img("000000101.img", backgrounds_map()),
            ]
        ],
    )
    w.write_tree(data / "String", stub=[], parts=[strings()])
    w.write_pack(data / "Packs" / "Mob_00000.ms", [snail()])
    return data


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A store holding the client's extraction, with its catalogue."""
    base = tmp_path_factory.mktemp("render")
    root = base / "store"
    extract(write_render_client(base / "Data"), root, catalogue=build_catalogue)
    return root


@pytest.fixture
def cat(root: Path) -> Iterator[Catalogue]:
    with Catalogue.latest(root) as catalogue:
        yield catalogue


def pixel(screen: Pixels, x: int, y: int, vr: tuple[int, int, int, int]) -> Rgba:
    """The pixel at virtual `(x, y)` of a screen of the VR bounds `vr`."""
    r, g, b, a = (int(v) for v in screen[y - vr[1], x - vr[0]])
    return r, g, b, a


def layers_at(screen: Pixels, x: int, y: int) -> Rgba:
    return pixel(screen, x, y, LAYERS_VR)


def backgrounds_at(screen: Pixels, x: int, y: int) -> Rgba:
    return pixel(screen, x, y, BACKGROUNDS_VR)


def read_png(path: Path) -> Pixels:
    """A PNG's pixels, as RGBA."""
    read = cv2.imdecode(
        np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED
    )
    assert read is not None
    return np.asarray(cv2.cvtColor(read, cv2.COLOR_BGRA2RGBA), dtype=np.uint8)


# --- the screen --------------------------------------------------------------


def test_the_screen_is_the_vr_bounds_with_their_top_left_at_pixel_0_0(
    cat: Catalogue,
) -> None:
    screen = render_map(cat, LAYERS)

    assert screen.shape == (200, 400, 4)
    assert screen.dtype == np.uint8
    # The tile at (0, 0), origin (1, 1), starts at virtual (-1, -1): pixel
    # (99, 49), with nothing left of it or above it.
    assert tuple(screen[49, 99]) == RED
    assert tuple(screen[49, 98]) == NOTHING
    assert tuple(screen[48, 99]) == NOTHING


def test_a_map_is_rendered_by_name_or_by_id(cat: Catalogue) -> None:
    by_name = render_map(cat, "Layers")
    by_full_name = render_map(cat, "Test Road: Layers")
    by_id = render_map(cat, LAYERS)

    assert np.array_equal(by_name, by_id)
    assert np.array_equal(by_full_name, by_id)


def test_an_unknown_map_raises_lookup_error(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="Layers"):
        render_map(cat, "Layerz")


# --- tiles and objects -------------------------------------------------------


def test_a_tile_draws_its_pixels_at_its_position_less_its_origin(
    cat: Catalogue,
) -> None:
    screen = render_map(cat, LAYERS)

    # Tile 0: 4x2 red, origin (1, 1), at (0, 0): virtual x -1 to 2, y -1 to 0.
    assert [layers_at(screen, x, -1) for x in range(-1, 3)] == [RED] * 4
    assert layers_at(screen, -2, -1) == NOTHING
    assert layers_at(screen, -1, 1) == NOTHING


def test_overlapping_tiles_are_drawn_by_z_not_by_the_maps_order(
    cat: Catalogue,
) -> None:
    """Tile 1 comes later in the map but has a lower `z`: tile 0 covers it."""
    screen = render_map(cat, LAYERS)

    assert layers_at(screen, 2, 0) == RED
    assert layers_at(screen, 3, 0) == GREEN


def test_a_layers_tiles_are_drawn_over_its_objects_whatever_their_z(
    cat: Catalogue,
) -> None:
    """The yellow box, `z` 9, is under tile 1 where they meet."""
    screen = render_map(cat, LAYERS)

    assert layers_at(screen, 4, 1) == GREEN
    assert layers_at(screen, 4, 2) == YELLOW


def test_a_later_layer_is_drawn_over_an_earlier_one(cat: Catalogue) -> None:
    screen = render_map(cat, LAYERS)

    assert layers_at(screen, 5, 0) == YELLOW


def test_an_object_puts_its_origin_at_its_position(cat: Catalogue) -> None:
    """Blue left column, origin (1, 2), at (50, 20): from (49, 18)."""
    screen = render_map(cat, LAYERS)

    assert [layers_at(screen, x, 18) for x in range(48, 53)] == [
        NOTHING,
        BLUE,
        WHITE,
        WHITE,
        NOTHING,
    ]
    assert layers_at(screen, 50, 19) == WHITE
    assert layers_at(screen, 50, 20) == NOTHING


def test_a_flipped_object_mirrors_about_its_position(cat: Catalogue) -> None:
    """The same object at (80, 20), flipped: its blue column is at x 80."""
    screen = render_map(cat, LAYERS)

    assert [layers_at(screen, x, 18) for x in range(77, 82)] == [
        NOTHING,
        WHITE,
        WHITE,
        BLUE,
        NOTHING,
    ]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (0, {(120, 0): RED, (120, -1): NOTHING}),
        (3, {(120, -1): BLUE, (120, 0): NOTHING}),
    ],
)
def test_an_animated_object_is_drawn_at_frame_modulo_its_frame_count(
    cat: Catalogue, frame: int, expected: dict[tuple[int, int], Rgba]
) -> None:
    """Frame 1 is blue with origin (0, 1): one pixel higher than frame 0."""
    screen = render_map(cat, LAYERS, frame=frame)

    assert {at: layers_at(screen, *at) for at in expected} == expected


# --- backgrounds -------------------------------------------------------------


def test_a_background_at_the_stored_rx_is_drawn_at_its_stored_position(
    cat: Catalogue,
) -> None:
    """Background 0, 3x3 red, `rx = ry = -100`, at (10, 10), under a dot."""
    screen = render_map(cat, BACKGROUNDS)

    assert STORED_AT_RX == -100
    assert backgrounds_at(screen, 11, 11) == RED
    assert backgrounds_at(screen, 12, 12) == RED
    assert backgrounds_at(screen, 13, 13) == NOTHING
    assert backgrounds_at(screen, 9, 9) == NOTHING


def test_a_background_with_rx_0_is_fixed_to_the_cameras_centre(
    cat: Catalogue,
) -> None:
    """Background 1, `rx = ry = 0`, at (10, 10): (10, 10) from (100, 50)."""
    screen = render_map(cat, BACKGROUNDS)

    assert backgrounds_at(screen, 110, 60) == GREEN
    assert backgrounds_at(screen, 111, 61) == GREEN
    assert backgrounds_at(screen, 109, 60) == NOTHING


def test_parallax_moves_a_background_by_its_share_of_the_cameras_centre(
    cat: Catalogue,
) -> None:
    """Background 2, `rx = ry = -50`, at (10, 10): half of (100, 50) on."""
    screen = render_map(cat, BACKGROUNDS)

    assert backgrounds_at(screen, 60, 35) == BLUE
    assert backgrounds_at(screen, 59, 35) == NOTHING


def test_the_reading_of_rx_flips_with_one_constant(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `STORED_AT_RX = 0`, background 1 is at its stored (10, 10)."""
    monkeypatch.setattr(placement, "STORED_AT_RX", 0)

    screen = render_map(cat, BACKGROUNDS)

    assert backgrounds_at(screen, 110, 60) == NOTHING
    assert backgrounds_at(screen, 11, 11) == GREEN


def test_the_camera_is_centred_on_the_map_for_any_viewport() -> None:
    for viewport in [(1366, 768), (800, 600), (100, 50)]:
        assert Camera.centred(Bounds(0, 0, 200, 100), viewport).centre == (100, 50)


def test_a_horizontally_tiled_background_repeats_every_cx_across_the_map(
    cat: Catalogue,
) -> None:
    """Background 3, 2x1 yellow, `type` 1, `cx` 50, at (5, 90)."""
    screen = render_map(cat, BACKGROUNDS)

    row = [backgrounds_at(screen, x, 90) for x in range(200)]
    assert [x for x, colour in enumerate(row) if colour == YELLOW] == [
        5,
        6,
        55,
        56,
        105,
        106,
        155,
        156,
    ]
    assert backgrounds_at(screen, 5, 91) == NOTHING


def test_a_vertically_tiled_background_with_cy_0_repeats_every_frame_height(
    cat: Catalogue,
) -> None:
    """Background 4, 1x10 white, `type` 2, at (190, 3): the whole column."""
    screen = render_map(cat, BACKGROUNDS)

    assert {backgrounds_at(screen, 190, y) for y in range(100)} == {WHITE}
    assert backgrounds_at(screen, 191, 50) == NOTHING


def test_a_backgrounds_alpha_makes_it_see_through(cat: Catalogue) -> None:
    screen = render_map(cat, BACKGROUNDS)

    assert backgrounds_at(screen, 30, 80) == (255, 0, 0, 128)


def test_a_flipped_background_mirrors_about_its_position(cat: Catalogue) -> None:
    """Background 6, red then green, at (70, 80), flipped."""
    screen = render_map(cat, BACKGROUNDS)

    assert [backgrounds_at(screen, x, 80) for x in (68, 69, 70)] == [
        GREEN,
        RED,
        NOTHING,
    ]


def test_backgrounds_behind_go_under_layers_and_those_in_front_over_them(
    cat: Catalogue,
) -> None:
    screen = render_map(cat, BACKGROUNDS)

    assert backgrounds_at(screen, 10, 10) == YELLOW
    assert backgrounds_at(screen, 150, 50) == BLUE


def test_tiling_needs_a_known_background_type() -> None:
    item = MapLayer(
        "back",
        None,
        0,
        None,
        0,
        0,
        False,
        None,
        (),
        Background(8, 0, 0, 0, 0, 255, False),
    )

    with pytest.raises(ValueError, match="type 8"):
        placement.copies(item, 0, 0, (1, 1), Bounds(0, 0, 10, 10))


# --- overlays ----------------------------------------------------------------


def test_without_overlays_nothing_but_the_map_is_drawn(cat: Catalogue) -> None:
    screen = render_map(cat, LAYERS)

    assert layers_at(screen, 240, 60) == NOTHING
    assert layers_at(screen, 270, 20) == NOTHING
    assert layers_at(screen, 280, 100) == NOTHING
    assert layers_at(screen, 149, 57) == NOTHING


def test_overlays_draw_footholds_ropes_and_portals_at_their_coordinates(
    cat: Catalogue,
) -> None:
    screen = render_map(cat, LAYERS, overlays=True)

    assert layers_at(screen, 240, 60) == FOOTHOLD["map"]
    assert layers_at(screen, 240, 61) != FOOTHOLD["map"]
    assert layers_at(screen, 270, 20) == ROPE["map"]
    assert layers_at(screen, 280, 100) == PORTAL
    # The foothold on the object at (50, 20), and on tile 1 at (2, 0).
    assert layers_at(screen, 50, 20) == FOOTHOLD["object"]
    assert layers_at(screen, 3, 5) == FOOTHOLD["tile"]


def test_overlays_draw_each_spawn_as_its_mobs_first_stand_frame(
    cat: Catalogue,
) -> None:
    """The Snail's stand frame, 4x3, origin (1, 3), blue on its left."""
    screen = render_map(cat, LAYERS, overlays=True)

    # At (150, 60): from (149, 57).
    assert layers_at(screen, 149, 57) == BLUE
    assert layers_at(screen, 150, 57) == RED
    assert layers_at(screen, 148, 57) == NOTHING
    # Flipped at (200, 60): mirrored about x 200, blue there.
    assert layers_at(screen, 200, 57) == BLUE
    assert layers_at(screen, 197, 57) == RED
    # The NPC has no sprite in the catalogue: a dot.
    assert layers_at(screen, 130, 100) == NO_SPRITE


def test_hitboxes_draw_each_spawns_lt_rb_box_mirrored_with_it(
    cat: Catalogue,
) -> None:
    """`lt` (-1, -3), `rb` (3, 0): from (149, 57) to (153, 60) at (150, 60)."""
    screen = render_map(cat, LAYERS, hitboxes=True)

    assert layers_at(screen, 153, 58) == HITBOX
    assert layers_at(screen, 151, 60) == HITBOX
    assert layers_at(screen, 151, 58) == RED
    # Flipped at (200, 60): from (197, 57) to (201, 60).
    assert layers_at(screen, 201, 58) == HITBOX
    assert layers_at(screen, 197, 58) == HITBOX
    # The other overlays aren't drawn.
    assert layers_at(screen, 240, 60) == NOTHING


# --- scale, the store and the command line ----------------------------------


@pytest.mark.parametrize(
    ("scale", "shape"), [(0.5, (100, 200, 4)), (2.0, (400, 800, 4))]
)
def test_scale_multiplies_both_sides(
    cat: Catalogue, scale: float, shape: tuple[int, int, int]
) -> None:
    screen = render_map(cat, LAYERS, scale=scale)

    assert screen.shape == shape


def test_overlays_are_drawn_at_the_scaled_coordinates(cat: Catalogue) -> None:
    screen = render_map(cat, LAYERS, scale=2.0, overlays=True)

    # Virtual (240, 60) is pixel (340, 110), times 2.
    assert tuple(screen[220, 680]) == FOOTHOLD["map"]
    # The tile at virtual (0, -1) is pixel (100, 49), times 2.
    assert tuple(screen[98, 200]) == RED


def test_a_scale_that_isnt_positive_is_an_error(cat: Catalogue) -> None:
    with pytest.raises(ValueError, match="positive"):
        render_map(cat, LAYERS, scale=0)


def test_an_image_missing_from_the_store_is_an_error_naming_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    extract(write_render_client(tmp_path / "Data"), root, catalogue=build_catalogue)
    with Catalogue.latest(root) as cat:
        name = cat.map_layers(LAYERS)[0].frames[0].image
        assert name is not None
        cat.store.images.path(name).unlink()

        with pytest.raises(RenderError, match=name):
            render_map(cat, LAYERS)


def test_a_background_type_this_doesnt_know_is_an_error_naming_the_map(
    cat: Catalogue,
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(placement, "TYPES", range(0))

    with pytest.raises(RenderError, match="map 101: a background of type 0"):
        render_map(cat, BACKGROUNDS)
    assert main(["render", str(BACKGROUNDS), "--root", str(root)]) == 1
    assert "map 101" in capsys.readouterr().err


def test_write_png_round_trips_the_pixels(cat: Catalogue, tmp_path: Path) -> None:
    screen = render_map(cat, BACKGROUNDS)
    path = tmp_path / "deep" / "out.png"

    write_png(screen, path)

    assert np.array_equal(read_png(path), screen)


def test_render_writes_the_png_to_the_stores_renders_by_default(
    root: Path, cat: Catalogue, capsys: pytest.CaptureFixture[str]
) -> None:
    path = render_path(cat, LAYERS)
    path.unlink(missing_ok=True)

    code = main(["render", "Layers", "--root", str(root)])

    assert code == 0
    assert path == root.resolve() / "renders" / "100.png"
    assert path.is_file()
    assert str(path) in capsys.readouterr().out


def test_render_takes_overlays_hitboxes_scale_and_out(
    root: Path, cat: Catalogue, tmp_path: Path
) -> None:
    out = tmp_path / "henesys.png"

    code = main(
        [
            "render",
            str(LAYERS),
            "--overlays",
            "--hitboxes",
            "--scale",
            "0.5",
            "--out",
            str(out),
            "--root",
            str(root),
        ]
    )

    assert code == 0
    expected = render_map(cat, LAYERS, scale=0.5, overlays=True, hitboxes=True)
    assert np.array_equal(read_png(out), expected)


def test_render_of_an_unknown_map_is_an_error(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["render", "Layerz", "--root", str(root)])

    assert code == 1
    assert "Layers" in capsys.readouterr().err


def test_render_rejects_a_scale_that_isnt_positive(root: Path) -> None:
    with pytest.raises(SystemExit):
        main(["render", "Layers", "--scale", "0", "--root", str(root)])
