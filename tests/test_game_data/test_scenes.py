"""
`game_data.scenes`: synthetic screens composed from a synthetic client's
catalogue and image store.

`write_scenes_client` writes a client of three maps, every value invented,
whose images are blocks of plain colours:

- `200`, "Scene Road: Field", VR `(0, 0)` to `(600, 300)`. A grey background
  tiled over the whole map, a red one fixed to the camera's centre, and a
  50x50 white one fixed to the map at (300, 150). Two footholds: `1`, flat at y 250 from x 0 to 300, then `2`, up to y 150 at x
  600. A Block spawns on `1` with `[rx0, rx1] = [20, 500]`, so it walks onto
  `2`; a Bat, which flies, on `1` in `[100, 200]`; a Crab in `[400, 500]`;
  and a Ghost, which has no sprite.
- `201`, "Scene Road: Small", VR `(0, 0)` to `(100, 50)`, all white.
- `202`, "Scene Road: Twins": a Mr. Snail and a Mr Snail.

The Crab's frame has a `head`, one right of its origin and four up. The
occluders: a Consume item whose icon is 8x8 green and a Cash one's 8x8 white,
both at origin `(-12, 8)`, so a drop's icon is centred on its `x`, its bottom
on the ground; a meso of two yellow frames, 6x6 and 2x6, likewise; and the
digit sets `NoRed0`, each digit 12x10 blue at origin `(6, 10)`, and `NoRed1`,
16x14 red at `(8, 14)`.

Most tests use a 200 by 100 client, so that the view is smaller than `200`.
"""

import itertools
import logging
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture, MockType

from game_data.catalogue import Bounds, Catalogue, build_catalogue
from game_data.extraction import extract
from game_data.render import Camera, Images, render_map
from game_data.scenes import (
    SCENES_VERSION,
    Label,
    Overlay,
    Placement,
    SceneError,
    class_name,
    compose,
    compose_scene,
    draw_mobs,
    map_classes,
    occluders,
)
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_catalogue import foothold_tree
from tests.test_game_data.test_catalogue_mobs_skills import mob_info
from tests.test_game_data.test_render import (
    BLUE,
    GREEN,
    NOTHING,
    RED,
    WHITE,
    YELLOW,
    Rgba,
    image,
    origin,
    solid,
)

FIELD = 200
SMALL = 201
TWINS = 202
FIELD_VR = Bounds(0, 0, 600, 300)
CLIENT = (200, 100)

GREY: Rgba = (128, 128, 128, 255)

BLOCK = 100100
BAT = 100200
GHOST = 100300
CRAB = 100400


def _ints(**values: int) -> list[w.Property]:
    return [w.Int(key, value) for key, value in values.items()]


def _numbered(name: str, *children: list[w.Property]) -> w.Prop:
    return w.Prop(name, [w.Prop(str(n), list(c)) for n, c in enumerate(children)])


def _info(vr: tuple[int, int, int, int]) -> w.Prop:
    keys = ("VRLeft", "VRTop", "VRRight", "VRBottom")
    return w.Prop("info", [w.Int(key, value) for key, value in zip(keys, vr)])


def _back(no: int, **values: int) -> list[w.Property]:
    defaults = {"x": 0, "y": 0, "rx": -100, "ry": -100, "type": 0, "cx": 0, "cy": 0}
    fixed = {"no": no, "a": 255, "front": 0, "ani": 0, "f": 0}
    return [w.String("bS", "stest"), *_ints(**defaults | fixed | values)]


def _mob(mob_id: int, x: int, rx0: int, rx1: int, fh: int = 1) -> list[w.Property]:
    return [
        w.String("type", "m"),
        w.String("id", f"{mob_id:07d}"),
        *_ints(x=x, y=250, cy=250, fh=fh, rx0=rx0, rx1=rx1, f=0),
    ]


def field_map() -> list[w.Property]:
    return [
        _info((0, 0, 600, 300)),
        foothold_tree((1, 0, 250, 300, 250, 0, 2), (2, 300, 250, 600, 150, 1, 0)),
        _numbered(
            "life",
            _mob(BLOCK, 50, 20, 500),
            _mob(BAT, 150, 100, 200),
            _mob(CRAB, 450, 400, 500, fh=2),
            _mob(GHOST, 60, 20, 100),
        ),
        _numbered(
            "back",
            _back(0, type=3),
            _back(1, rx=0, ry=0),
            _back(2, x=300, y=150),
        ),
    ]


def small_map() -> list[w.Property]:
    return [_info((0, 0, 100, 50)), _numbered("back", _back(2, type=3))]


def twins_map() -> list[w.Property]:
    return [
        _info((0, 0, 600, 300)),
        foothold_tree((1, 0, 250, 600, 250, 0, 0)),
        _numbered("life", _mob(100101, 50, 0, 100), _mob(100102, 50, 0, 100)),
    ]


def back_assets() -> list[w.Property]:
    return [
        w.Prop(
            "back",
            [
                solid("0", 50, 50, GREY, origin(0, 0)),
                solid("1", 2, 2, RED, origin(0, 0)),
                solid("2", 50, 50, WHITE, origin(0, 0)),
            ],
        )
    ]


def _action(name: str, *frames: w.Canvas) -> w.Prop:
    return w.Prop(name, list(frames))


def _block(name: str, colour: Rgba) -> w.Canvas:
    """A 10x10 block standing on its bottom middle."""
    return solid(
        name,
        10,
        10,
        colour,
        origin(5, 10),
        w.Vector("lt", -2, -2),
        w.Vector("rb", 2, 0),
    )


def ring() -> w.Canvas:
    """6x6: a transparent border around 4x4 opaque yellow, origin (3, 6)."""
    rows = [
        [YELLOW if 0 < x < 5 and 0 < y < 5 else NOTHING for x in range(6)]
        for y in range(6)
    ]
    return image("0", rows, origin(3, 6), w.Vector("lt", -3, -6), w.Vector("rb", 3, 0))


def mobs() -> list[w.Img]:
    return [
        w.Img(
            "Mob/0100100.img",
            [
                mob_info(level=1),
                _action("stand", _block("0", BLUE), _block("1", BLUE)),
                _action("move", _block("0", RED)),
                _action("attack1", _block("0", YELLOW)),
            ],
        ),
        w.Img(
            "Mob/0100200.img",
            [mob_info(w.Int("flySpeed", 30), level=2), _action("stand", ring())],
        ),
        w.Img("Mob/0100300.img", [mob_info(level=3)]),
        w.Img(
            "Mob/0100400.img",
            [
                mob_info(level=4),
                _action(
                    "stand",
                    solid("0", 4, 4, YELLOW, origin(2, 4), w.Vector("head", 1, -4)),
                ),
            ],
        ),
        w.Img(
            "Mob/0100101.img",
            [mob_info(level=5), _action("stand", solid("0", 2, 2, RED, origin(1, 2)))],
        ),
        w.Img(
            "Mob/0100102.img",
            [mob_info(level=5), _action("stand", solid("0", 2, 2, RED, origin(1, 2)))],
        ),
    ]


def strings() -> list[w.Img]:
    def entry(map_id: int, name: str) -> w.Prop:
        return w.Prop(
            f"{map_id:09d}",
            [w.String("streetName", "Scene Road"), w.String("mapName", name)],
        )

    names = {
        BLOCK: "Block",
        BAT: "Bat",
        GHOST: "Ghost",
        CRAB: "Crab",
        100101: "Mr. Snail",
        100102: "Mr Snail",
    }
    return [
        w.Img(
            "Map.img",
            [
                w.Prop(
                    "test",
                    [
                        entry(FIELD, "Field"),
                        entry(SMALL, "Small"),
                        entry(TWINS, "Twins"),
                    ],
                )
            ],
        ),
        w.Img(
            "Mob.img",
            [
                w.Prop(str(mob_id), [w.String("name", name)])
                for mob_id, name in names.items()
            ],
        ),
    ]


def items() -> list[w.Dir]:
    def item(item_id: str, colour: Rgba) -> w.Prop:
        return w.Prop(
            item_id,
            [w.Prop("info", [solid("iconRaw", 8, 8, colour, origin(-12, 8))])],
        )

    meso = w.Prop(
        "iconRaw",
        [
            solid("0", 6, 6, YELLOW, origin(-13, 6)),
            solid("1", 2, 6, YELLOW, origin(-15, 6)),
        ],
    )
    return [
        w.Dir("Consume", [w.Img("0200.img", [item("02000000", GREEN)])]),
        w.Dir("Cash", [w.Img("0501.img", [item("05010000", WHITE)])]),
        w.Dir("Special", [w.Img("0900.img", [w.Prop("09000000", [meso])])]),
    ]


def basic_effects() -> list[w.Prop]:
    def digits(name: str, width: int, height: int, colour: Rgba) -> w.Prop:
        return w.Prop(
            name,
            [
                solid(str(d), width, height, colour, origin(width // 2, height))
                for d in range(10)
            ],
        )

    return [digits("NoRed0", 12, 10, BLUE), digits("NoRed1", 16, 14, RED)]


def write_scenes_client(data: Path) -> Path:
    """The client described above, in `data`."""
    w.write_tree(
        data / "Map",
        stub=[w.Dir("Map"), w.Dir("Back")],
        parts=[
            [
                w.Img("Physics.img", [w.Float("walkSpeed", 125.0)]),
                w.Dir("Back", [w.Img("stest.img", back_assets())]),
            ]
        ],
    )
    w.write_tree(data / "Map" / "Map", stub=[w.Dir("Map0")], ini=False)
    w.write_tree(
        data / "Map" / "Map" / "Map0",
        stub=[],
        parts=[
            [
                w.Img(f"{FIELD:09d}.img", field_map()),
                w.Img(f"{SMALL:09d}.img", small_map()),
                w.Img(f"{TWINS:09d}.img", twins_map()),
            ]
        ],
    )
    w.write_tree(data / "String", stub=[], parts=[strings()])
    w.write_pack(data / "Packs" / "Mob_00000.ms", mobs())
    w.write_tree(data / "Item", items(), ini=False)
    w.write_tree(data / "Effect", [w.Img("BasicEff.img", basic_effects())], ini=False)
    return data


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("scenes")
    root = base / "store"
    extract(write_scenes_client(base / "Data"), root, catalogue=build_catalogue)
    return root


@pytest.fixture
def cat(root: Path) -> Iterator[Catalogue]:
    with Catalogue.latest(root) as catalogue:
        yield catalogue


def rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


class Drawn:
    """Records what `compose_scene` hands `draw_mobs`, and the camera."""

    def __init__(self) -> None:
        self.placements: list[Placement] = []
        self.overlays: list[Overlay] = []
        self.cameras: list[Camera] = []


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> Drawn:
    record = Drawn()
    draw, camera = compose.draw_mobs, compose.draw_camera

    def recording_draw(
        view: np.ndarray,
        placements: Sequence[Placement],
        images: Images,
        overlays: Sequence[Overlay] = (),
    ) -> tuple[Label | None, ...]:
        record.placements.extend(placements)
        record.overlays.extend(overlays)
        return draw(view, placements, images, overlays)

    def recording_camera(
        bounds: Bounds, client: tuple[int, int], generator: np.random.Generator
    ) -> Camera:
        record.cameras.append(camera(bounds, client, generator))
        return record.cameras[-1]

    monkeypatch.setattr(compose, "draw_mobs", recording_draw)
    monkeypatch.setattr(compose, "draw_camera", recording_camera)
    return record


def fix_camera(monkeypatch: pytest.MonkeyPatch, camera: Camera) -> None:
    monkeypatch.setattr(compose, "draw_camera", lambda *_: camera)


def rgb(colour: Rgba) -> tuple[int, int, int]:
    return colour[0], colour[1], colour[2]


def at(view: np.ndarray, x: int, y: int) -> tuple[int, int, int]:
    r, g, b = (int(v) for v in view[y, x])
    return r, g, b


# --- the scene ---------------------------------------------------------------


def test_a_scene_is_an_rgb_image_of_the_clients_size(cat: Catalogue) -> None:
    scene = compose_scene(cat, FIELD, rng(), client=CLIENT)

    assert scene.image.shape == (100, 200, 3)
    assert scene.image.dtype == np.uint8


def test_the_default_client_is_1366_by_768(cat: Catalogue) -> None:
    scene = compose_scene(cat, SMALL, rng())

    assert scene.image.shape == (768, 1366, 3)


def test_a_map_is_composed_by_name_or_id(cat: Catalogue) -> None:
    by_name = compose_scene(cat, "Field", rng(3), client=CLIENT)
    by_id = compose_scene(cat, FIELD, rng(3), client=CLIENT)

    assert np.array_equal(by_name.image, by_id.image)
    assert by_name.labels == by_id.labels


def test_scenes_version_is_a_positive_int() -> None:
    assert isinstance(SCENES_VERSION, int)
    assert SCENES_VERSION >= 1


@pytest.mark.parametrize("mobs", [(-1, 3), (4, 2)])
def test_a_mob_range_must_be_ordered_and_not_negative(
    cat: Catalogue, mobs: tuple[int, int]
) -> None:
    with pytest.raises(ValueError, match="mobs"):
        compose_scene(cat, FIELD, rng(), client=CLIENT, mobs=mobs)


# --- the view ----------------------------------------------------------------


def test_the_camera_never_leaves_the_vr_bounds_and_reaches_both_edges() -> None:
    generator = rng()
    cameras = [compose.draw_camera(FIELD_VR, CLIENT, generator) for _ in range(500)]

    assert all(c.width == 200 and c.height == 100 for c in cameras)
    assert all(0 <= c.left and c.left + 200 <= 600 for c in cameras)
    assert all(0 <= c.top and c.top + 100 <= 300 for c in cameras)
    # Centres drawn near an edge are clamped onto it.
    assert {c.left for c in cameras} >= {0, 400}
    assert {c.top for c in cameras} >= {0, 200}
    assert len({c.left for c in cameras}) > 50


def test_on_an_axis_narrower_than_the_view_the_map_is_centred() -> None:
    generator = rng()
    cameras = {
        compose.draw_camera(Bounds(0, 0, 600, 50), CLIENT, generator) for _ in range(50)
    }

    assert {c.top for c in cameras} == {-25}
    assert len({c.left for c in cameras}) > 1


def test_a_map_smaller_than_the_view_is_centred_on_black(cat: Catalogue) -> None:
    """`201` is 100x50 white: it fills (50, 25) to (150, 75), black around."""
    view = compose_scene(cat, SMALL, rng(), client=CLIENT).image

    assert {at(view, x, y) for x in range(50, 150) for y in range(25, 75)} == {
        rgb(WHITE)
    }
    outside = np.ones((100, 200), dtype=bool)
    outside[25:75, 50:150] = False
    assert not view[outside].any()


def test_the_view_is_render_map_at_the_scenes_camera_cropped(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    camera = Camera(150, 100, 200, 100)
    fix_camera(monkeypatch, camera)

    view = compose_scene(cat, FIELD, rng(), client=CLIENT, mobs=(0, 0)).image

    screen = render_map(cat, FIELD, camera=camera)
    assert np.array_equal(view, screen[100:200, 150:350, :3])
    # The red background is fixed to the camera's centre, (250, 150).
    assert at(view, 100, 50) == rgb(RED)
    assert at(view, 99, 50) == rgb(GREY)


def test_cameras_none_renders_the_map_for_each_scene(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    spy = mocker.spy(compose, "render_map")
    generator = rng()

    for _ in range(5):
        compose_scene(cat, FIELD, generator, client=CLIENT, mobs=(0, 0))

    assert spy.call_count == 5


def test_cameras_n_renders_n_cameras_once_and_each_scene_picks_one(
    cat: Catalogue, drawn: Drawn, mocker: MockerFixture
) -> None:
    spy = mocker.spy(compose, "render_map")
    generator = rng()

    views = [
        compose_scene(cat, FIELD, generator, client=CLIENT, mobs=(0, 0), cameras=3)
        for _ in range(30)
    ]

    assert spy.call_count == 3
    assert len(set(drawn.cameras)) == 3
    crops = {
        render_map(cat, FIELD, camera=c)[
            c.top : c.top + c.height, c.left : c.left + c.width, :3
        ].tobytes()
        for c in drawn.cameras
    }
    assert {view.image.tobytes() for view in views} <= crops


def test_mobs_drawn_on_a_shared_camera_dont_stay_on_it(cat: Catalogue) -> None:
    generator = rng()

    def compose_one(mobs: tuple[int, int]) -> np.ndarray:
        return compose_scene(
            cat, FIELD, generator, client=(600, 300), mobs=mobs, cameras=1
        ).image

    empty = compose_one((0, 0))
    crowded = compose_one((15, 15))

    assert not np.array_equal(crowded, empty)
    assert np.array_equal(compose_one((0, 0)), empty)


def test_cameras_must_be_positive(cat: Catalogue) -> None:
    with pytest.raises(ValueError, match="cameras"):
        compose_scene(cat, FIELD, rng(), client=CLIENT, cameras=0)


# --- the mobs ----------------------------------------------------------------


def test_the_number_of_mobs_is_drawn_from_the_range(
    cat: Catalogue, drawn: Drawn
) -> None:
    counts: list[int] = []
    generator = rng()
    for _ in range(60):
        before = len(drawn.placements)
        compose_scene(cat, FIELD, generator, client=(600, 300), mobs=(2, 5))
        counts.append(len(drawn.placements) - before)

    assert set(counts) == {2, 3, 4, 5}


def test_mobs_stand_on_their_spawns_foothold_within_its_range(
    cat: Catalogue, drawn: Drawn
) -> None:
    """The Block's range runs off foothold 1 onto 2, which climbs 100 in 300."""
    generator = rng()
    for _ in range(40):
        compose_scene(cat, FIELD, generator, client=(600, 300), mobs=(15, 15))

    blocks = [p for p in drawn.placements if p.mob.id == BLOCK]
    assert blocks
    # The view is the whole map, so view pixels are virtual coordinates.
    for block in blocks:
        assert 20 <= block.x <= 500
        expected = 250 if block.x <= 300 else round(250 - (block.x - 300) / 3)
        assert block.y == expected
    assert min(b.x for b in blocks) < 100
    assert max(b.x for b in blocks) > 400
    crabs = [p for p in drawn.placements if p.mob.id == CRAB]
    assert crabs
    assert all(400 <= c.x <= 500 for c in crabs)


def test_a_flying_mob_is_raised_up_to_150_px_within_the_view(
    cat: Catalogue, drawn: Drawn
) -> None:
    generator = rng()
    for _ in range(40):
        compose_scene(cat, FIELD, generator, client=(600, 300), mobs=(15, 15))

    lifts = [250 - p.y for p in drawn.placements if p.mob.id == BAT]
    assert lifts
    assert all(0 <= lift <= 150 for lift in lifts)
    assert max(lifts) > 100
    assert min(lifts) < 50


def test_a_flying_mob_is_raised_no_higher_than_the_views_top(
    cat: Catalogue, drawn: Drawn, monkeypatch: pytest.MonkeyPatch
) -> None:
    fix_camera(monkeypatch, Camera(0, 200, 200, 100))
    generator = rng()
    for _ in range(20):
        compose_scene(cat, FIELD, generator, client=CLIENT, mobs=(15, 15))

    bats = [p for p in drawn.placements if p.mob.id == BAT]
    assert bats
    assert all(p.y >= 0 for p in bats)
    assert any(p.y == 0 for p in bats)


def test_only_spawns_whose_range_overlaps_the_view_are_drawn(
    cat: Catalogue, drawn: Drawn, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The view's columns are 0 to 199: the Crab's `[400, 500]` misses them."""
    fix_camera(monkeypatch, Camera(0, 200, 200, 100))
    generator = rng()
    for _ in range(20):
        compose_scene(cat, FIELD, generator, client=CLIENT, mobs=(15, 15))

    assert {p.mob.id for p in drawn.placements} == {BLOCK, BAT}


def test_a_mobs_action_frame_and_facing_are_drawn_among_those_it_has(
    cat: Catalogue, drawn: Drawn
) -> None:
    """The Block has `stand` of two frames, `move`, and `attack1`, never drawn."""
    generator = rng()
    for _ in range(40):
        compose_scene(cat, FIELD, generator, client=(600, 300), mobs=(15, 15))

    blocks = [p for p in drawn.placements if p.mob.id == BLOCK]
    assert {(p.action, p.frame) for p in blocks} == {
        ("stand", 0),
        ("stand", 1),
        ("move", 0),
    }
    assert {p.flip for p in blocks} == {False, True}


def test_mobs_are_drawn_in_a_random_order(cat: Catalogue, drawn: Drawn) -> None:
    generator = rng()
    orders: set[tuple[int, ...]] = set()
    for _ in range(20):
        before = len(drawn.placements)
        compose_scene(cat, FIELD, generator, client=(600, 300), mobs=(4, 4))
        orders.add(tuple(p.mob.id for p in drawn.placements[before:]))

    assert len(orders) > 5


# --- labels ------------------------------------------------------------------


def test_a_box_is_the_opaque_pixels_bounds_not_the_hitbox(cat: Catalogue) -> None:
    """The ring's opaque 4x4 is (1, 1) to (5, 5) of 6x6, origin (3, 6)."""
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    bat = cat.mob(BAT)

    (label,) = draw_mobs(
        view, [Placement(bat, "stand", 0, 50, 60, False)], Images(cat.store.images)
    )

    assert label == Label("Bat", (48, 55, 52, 59), 1.0)
    assert at(view, 48, 55) == rgb(YELLOW)
    assert at(view, 47, 54) == (0, 0, 0)


def test_a_box_is_clipped_to_the_view(cat: Catalogue) -> None:
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    block = cat.mob(BLOCK)

    (label,) = draw_mobs(
        view, [Placement(block, "stand", 0, 2, 5, False)], Images(cat.store.images)
    )

    assert label is not None
    assert label.box == (0, 0, 7, 5)
    assert label.visible == 1.0


def test_a_mob_with_nothing_in_the_view_has_no_label(cat: Catalogue) -> None:
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    block = cat.mob(BLOCK)

    labels = draw_mobs(
        view, [Placement(block, "stand", 0, 500, 50, False)], Images(cat.store.images)
    )

    assert labels == (None,)
    assert not view.any()


def test_a_mob_half_covered_by_a_later_one_is_half_visible(cat: Catalogue) -> None:
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    block = cat.mob(BLOCK)
    placements = [
        Placement(block, "stand", 0, 50, 50, False),
        Placement(block, "move", 0, 55, 50, False),
    ]

    under, over = draw_mobs(view, placements, Images(cat.store.images))

    assert under is not None
    assert over is not None
    assert under.visible == pytest.approx(0.5, abs=0.05)
    assert over.visible == 1.0
    assert under.box == (45, 40, 55, 50)
    assert at(view, 47, 45) == rgb(BLUE)
    assert at(view, 52, 45) == rgb(RED)


def test_a_flipped_mob_mirrors_about_its_x(cat: Catalogue) -> None:
    """The ring is symmetric, so it spans the same pixels either way."""
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    bat = cat.mob(BAT)

    (label,) = draw_mobs(
        view, [Placement(bat, "stand", 0, 50, 60, True)], Images(cat.store.images)
    )

    # Flipped, the 6-wide ring's left is 50 - (6 - 3) = 47; opaque from 48.
    assert label is not None
    assert label.box == (48, 55, 52, 59)


def test_a_label_under_the_floor_is_dropped_but_the_mob_stays_drawn(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first Block shows 2 of its 10 columns: 0.2, under 0.3."""
    block = cat.mob(BLOCK)
    fix_camera(monkeypatch, Camera(0, 200, 200, 100))
    placements = [
        Placement(block, "stand", 0, 50, 50, False),
        Placement(block, "move", 0, 52, 50, False),
    ]
    monkeypatch.setattr(compose, "_placements", lambda *_: placements)

    scene = compose_scene(cat, FIELD, rng(), client=CLIENT, mobs=(2, 2))

    assert scene.labels == (Label("Block", (47, 40, 57, 50), 1.0),)
    assert at(scene.image, 46, 45) == rgb(BLUE)

    lowered = compose_scene(
        cat, FIELD, rng(), client=CLIENT, mobs=(2, 2), visibility_floor=0.1
    )
    assert [label.visible for label in lowered.labels] == [
        pytest.approx(0.2),
        1.0,
    ]


# --- class names -------------------------------------------------------------


def test_class_names_drop_spaces_and_dots() -> None:
    assert class_name("Mr. Snail") == "MrSnail"
    assert class_name("Jr. Necki") == "JrNecki"
    assert class_name("Snail") == "Snail"


def test_two_species_of_one_class_name_in_a_map_raise_naming_both(
    cat: Catalogue,
) -> None:
    with pytest.raises(SceneError, match="100101 and 100102"):
        compose_scene(cat, TWINS, rng(), client=CLIENT)


def test_a_species_with_no_sprite_is_left_out_with_a_warning(
    cat: Catalogue, drawn: Drawn, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger=compose.__name__):
        for seed in range(10):
            compose_scene(cat, FIELD, rng(seed), client=(600, 300), mobs=(15, 15))

    assert GHOST not in {p.mob.id for p in drawn.placements}
    assert any(
        "Ghost" in r.getMessage() and str(GHOST) in r.getMessage()
        for r in caplog.records
    )


# --- occluders ---------------------------------------------------------------

BOTH = {"drops": (0, 5), "damage": (0, 5)}


def calls(spy: MockType) -> list[tuple[int, int]]:
    """The `(x, y)` each call of a spied `drop` or `damage` was given."""
    found: list[tuple[int, int]] = []
    for call in spy.call_args_list:
        found.append((call.args[2], call.args[3]))
    return found


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ({"fog": (0, 1)}, "no occluder 'fog'; the occluders are drops, damage"),
        ({"drops": (3, 1)}, r"occluders\['drops'\] must be \(min, max\)"),
        ({"damage": (-1, 2)}, r"occluders\['damage'\] must be \(min, max\)"),
    ],
)
def test_occluders_are_known_kinds_with_ordered_ranges(
    cat: Catalogue, given: dict[str, tuple[int, int]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compose_scene(cat, FIELD, rng(), client=CLIENT, occluders=given)


def test_no_occluders_are_drawn_unless_asked_for(
    cat: Catalogue, drawn: Drawn, mocker: MockerFixture
) -> None:
    drops = mocker.spy(occluders, "drop")
    damage = mocker.spy(occluders, "damage")

    for seed in range(5):
        compose_scene(cat, FIELD, rng(seed), client=(600, 300), mobs=(5, 5))
        compose_scene(
            cat, FIELD, rng(seed), client=(600, 300), mobs=(5, 5), occluders={}
        )

    assert drops.call_count == damage.call_count == 0
    assert drawn.overlays == []


def test_the_number_of_drops_is_drawn_from_the_range(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    spy = mocker.spy(occluders, "drop")
    counts: set[int] = set()
    generator = rng()
    for _ in range(40):
        before = spy.call_count
        compose_scene(
            cat, FIELD, generator, client=(600, 300), occluders={"drops": (2, 4)}
        )
        counts.add(spy.call_count - before)

    assert counts == {2, 3, 4}


def test_drops_lie_on_a_spawns_foothold_within_its_range(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    """The view is the whole map; spawns run over `[20, 500]`, as mobs do."""
    spy = mocker.spy(occluders, "drop")
    generator = rng()
    for _ in range(20):
        compose_scene(
            cat, FIELD, generator, client=(600, 300), occluders={"drops": (5, 5)}
        )

    points = calls(spy)
    assert len(points) == 100
    for x, y in points:
        assert 20 <= x <= 500
        assert y == (250 if x <= 300 else round(250 - (x - 300) / 3))
    assert min(x for x, _ in points) < 100
    assert max(x for x, _ in points) > 400


def test_a_drop_is_a_meso_frame_or_an_items_icon_never_a_cash_items(
    cat: Catalogue,
) -> None:
    sprites = occluders.Sprites.read(cat)
    images = Images(cat.store.images)
    generator = rng()

    drops = [occluders.drop(sprites, images, 100, 80, generator) for _ in range(60)]

    shapes = {(d.pixels.shape[1], d.pixels.shape[0]) for d in drops}
    assert shapes == {(8, 8), (6, 6), (2, 6)}
    colours = {tuple(int(c) for c in d.pixels[0, 0]) for d in drops}
    assert colours == {GREEN, YELLOW}
    # Centred on x, the bottom on the ground: (-12, 8) in a 32-pixel slot.
    icon = next(d for d in drops if d.pixels.shape[1] == 8)
    assert (icon.left, icon.top) == (96, 72)


def test_a_drop_in_front_of_a_mob_counts_against_its_visible_one_behind_doesnt(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A drop over the Block's left half: 0.5 visible in front, 1.0 behind."""
    fix_camera(monkeypatch, Camera(0, 200, 200, 100))
    block = cat.mob(BLOCK)
    monkeypatch.setattr(
        compose, "_placements", lambda *_: [Placement(block, "stand", 0, 50, 50, False)]
    )
    half = np.zeros((10, 5, 4), dtype=np.uint8)
    half[...] = GREEN
    monkeypatch.setattr(occluders, "drop", lambda *_: Overlay(half, 45, 40))

    seen: set[float] = set()
    for seed in range(20):
        scene = compose_scene(
            cat, FIELD, rng(seed), client=CLIENT, occluders={"drops": (1, 1)}
        )
        (label,) = scene.labels
        seen.add(label.visible)
        assert label.box == (45, 40, 55, 50)
        expected = rgb(GREEN) if label.visible < 1 else rgb(BLUE)
        assert at(scene.image, 47, 45) == expected

    assert seen == {0.5, 1.0}


def test_draw_mobs_counts_overlays_over_a_mob(cat: Catalogue) -> None:
    view = np.zeros((100, 200, 3), dtype=np.uint8)
    half = np.zeros((10, 5, 4), dtype=np.uint8)
    half[...] = GREEN

    (label,) = draw_mobs(
        view,
        [Placement(cat.mob(BLOCK), "stand", 0, 50, 50, False)],
        Images(cat.store.images),
        [Overlay(half, 45, 40)],
    )

    assert label is not None
    assert label.visible == pytest.approx(0.5)
    assert label.box == (45, 40, 55, 50)
    assert at(view, 47, 45) == rgb(GREEN)
    assert at(view, 52, 45) == rgb(BLUE)


@pytest.mark.parametrize(("flip", "head"), [(False, (101, 76)), (True, (99, 76))])
def test_a_damage_number_is_above_the_mobs_head(
    cat: Catalogue,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    flip: bool,
    head: tuple[int, int],
) -> None:
    """The Crab at (100, 80) has its head at (1, -4), mirrored when flipped."""
    crab = cat.mob(CRAB)
    monkeypatch.setattr(
        compose, "_placements", lambda *_: [Placement(crab, "stand", 0, 100, 80, flip)]
    )
    spy = mocker.spy(occluders, "damage")

    compose_scene(cat, FIELD, rng(), client=CLIENT, occluders={"damage": (3, 3)})

    assert calls(spy) == [head] * 3


def test_without_a_head_a_number_is_above_the_middle_of_its_opaque_top(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """The ring at (50, 60) is drawn from (47, 54); opaque from (48, 55) to (52, 59)."""
    bat = cat.mob(BAT)
    monkeypatch.setattr(
        compose, "_placements", lambda *_: [Placement(bat, "stand", 0, 50, 60, False)]
    )
    spy = mocker.spy(occluders, "damage")

    compose_scene(cat, FIELD, rng(), client=CLIENT, occluders={"damage": (1, 1)})

    assert calls(spy) == [(50, 55)]


def test_damage_numbers_are_only_over_mobs_with_a_pixel_in_the_view(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """The view is 200x100: a Crab at (100, 80) is in it, one at (100, 300) not."""
    crab = cat.mob(CRAB)
    placements = [
        Placement(crab, "stand", 0, 100, 300, False),
        Placement(crab, "stand", 0, 100, 80, False),
    ]
    monkeypatch.setattr(compose, "_placements", lambda *_: placements)
    spy = mocker.spy(occluders, "damage")

    for seed in range(5):
        compose_scene(
            cat, FIELD, rng(seed), client=CLIENT, occluders={"damage": (4, 4)}
        )

    assert calls(spy) == [(101, 76)] * 20


def test_damage_numbers_need_a_drawn_mob(cat: Catalogue, mocker: MockerFixture) -> None:
    spy = mocker.spy(occluders, "damage")

    compose_scene(
        cat, FIELD, rng(), client=CLIENT, mobs=(0, 0), occluders={"damage": (3, 3)}
    )

    assert spy.call_count == 0


def test_a_damage_number_is_a_large_first_digit_then_small_ones_centred_above(
    cat: Catalogue,
) -> None:
    """`NoRed1`'s digits are 16x14, `NoRed0`'s 12x10; they overlap by 8."""
    sprites = occluders.Sprites.read(cat)
    images = Images(cat.store.images)
    generator = rng()
    lengths: set[int] = set()
    rises: set[int] = set()
    for _ in range(200):
        number = occluders.damage(sprites, images, 100, 80, generator)
        lengths.add(len(number))
        shapes = [(d.pixels.shape[1], d.pixels.shape[0]) for d in number]
        assert shapes == [(16, 14)] + [(12, 10)] * (len(number) - 1)
        bottoms = {number[0].top + 14} | {d.top + 10 for d in number[1:]}
        assert len(bottoms) == 1
        rises.add(80 - bottoms.pop())
        steps = [b.left - a.left for a, b in itertools.pairwise(number)]
        assert steps == [width - 8 for width, _ in shapes[:-1]]
        width = 16 + 4 * (len(number) - 1)
        assert number[0].left == 100 - width // 2

    assert lengths == set(range(1, occluders.DAMAGE_DIGITS + 1))
    assert min(rises) >= 0
    assert max(rises) <= occluders.DAMAGE_RISE
    assert len(rises) > 30


def test_digit_sets_pair_by_number_and_a_set_short_of_a_digit_is_left_out(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    full = cat.damage_digits()
    sprites = occluders.Sprites.read(cat)
    assert len(sprites.digits) == 1
    rest, first = sprites.digits[0]
    assert sorted(rest) == sorted(first) == list(range(10))

    mocker.patch.object(
        cat, "damage_digits", return_value=tuple(d for d in full if d.digit != 7)
    )
    assert occluders.Sprites.read(cat).digits == []


def test_occluders_the_catalogue_has_no_sprites_for_are_left_out_with_a_warning(
    cat: Catalogue,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(occluders.Sprites, "read", lambda *_: occluders.Sprites())
    spy = mocker.spy(occluders, "drop")

    with caplog.at_level(logging.WARNING, logger=compose.__name__):
        compose_scene(cat, FIELD, rng(), client=(600, 300), mobs=(3, 3), occluders=BOTH)

    assert spy.call_count == 0
    messages = [r.getMessage() for r in caplog.records]
    assert any("no sprites for drops" in m for m in messages)
    assert any("no sprites for damage" in m for m in messages)


def test_the_same_seed_gives_the_same_occluded_scene(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    spy = mocker.spy(occluders, "drop")

    def scenes(seed: int) -> list[tuple[bytes, tuple[Label, ...]]]:
        generator = rng(seed)
        return [
            (scene.image.tobytes(), scene.labels)
            for scene in (
                compose_scene(
                    cat, FIELD, generator, client=CLIENT, mobs=(3, 8), occluders=BOTH
                )
                for _ in range(3)
            )
        ]

    first = scenes(7)

    assert spy.call_count > 0
    assert scenes(7) == first
    assert scenes(8) != first


# --- determinism -------------------------------------------------------------


@pytest.mark.parametrize("cameras", [None, 2])
def test_the_same_seed_gives_the_same_scene_and_another_seed_another(
    cat: Catalogue, cameras: int | None
) -> None:
    def scenes(seed: int) -> list[tuple[bytes, tuple[Label, ...]]]:
        generator = rng(seed)
        return [
            (scene.image.tobytes(), scene.labels)
            for scene in (
                compose_scene(
                    cat, FIELD, generator, client=CLIENT, mobs=(3, 8), cameras=cameras
                )
                for _ in range(3)
            )
        ]

    first = scenes(7)

    assert scenes(7) == first
    assert scenes(8) != first
    assert any(labels for _, labels in first)


def test_map_classes_are_the_drawable_species_sorted_by_name(cat: Catalogue) -> None:
    assert map_classes(cat, FIELD) == ["Bat", "Block", "Crab"]


def test_map_classes_raise_for_two_species_of_one_name(cat: Catalogue) -> None:
    with pytest.raises(SceneError, match="share the class name"):
        map_classes(cat, TWINS)
