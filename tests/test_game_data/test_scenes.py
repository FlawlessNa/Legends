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
occluders: a Consume item (2000000) whose icon is 8x8 green and a Cash one's
(5010000) 8x8 white,
both at origin `(-12, 8)`, so a drop's icon is centred on its `x`, its bottom
on the ground; a meso of two yellow frames, 6x6 and 2x6, likewise; and the
digit sets `NoRed0`, each digit 12x10 blue at origin `(6, 10)`, and `NoRed1`,
16x14 red at `(8, 14)`.

Most tests use a 200 by 100 client, so that the view is smaller than `200`.
"""

import itertools
import logging
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture, MockType

from game_data.catalogue import Bounds, Catalogue, MapData, build_catalogue
from game_data.extraction import extract
from game_data.render import Camera, Images, render_map
from game_data.scenes import (
    SCENES_VERSION,
    Damage,
    Drops,
    Label,
    Overlay,
    Placement,
    SceneError,
    Spot,
    class_name,
    compose,
    compose_scene,
    draw_mobs,
    map_classes,
    occluders,
    scene_camera,
    spots,
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


# Every drawable spawn of `200` has a mob: the Block, the Bat and the Crab.
FULL = (1.0, 1.0)
EMPTY = (0.0, 0.0)
GREEN_ITEM = "item:2000000"
MESO = "meso:9000000"
RED_ONLY = ("NoRed0",)


class Drawn:
    """Records what `compose_scene` hands `draw_mobs`, and the camera."""

    def __init__(self) -> None:
        self.placements: list[Placement] = []
        self.overlays: list[Overlay] = []
        self.cameras: list[Camera] = []


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> Drawn:
    record = Drawn()
    draw, camera = compose.draw_mobs, compose.scene_camera

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
        data: MapData,
        found: Sequence[Spot],
        client: tuple[int, int],
        generator: np.random.Generator,
    ) -> Camera:
        record.cameras.append(camera(data, found, client, generator))
        return record.cameras[-1]

    monkeypatch.setattr(compose, "draw_mobs", recording_draw)
    monkeypatch.setattr(compose, "scene_camera", recording_camera)
    return record


def fix_camera(monkeypatch: pytest.MonkeyPatch, camera: Camera) -> None:
    monkeypatch.setattr(compose, "scene_camera", lambda *_: camera)


def rgb(colour: Rgba) -> tuple[int, int, int]:
    return colour[0], colour[1], colour[2]


def at(view: np.ndarray, x: int, y: int) -> tuple[int, int, int]:
    r, g, b = (int(v) for v in view[y, x])
    return r, g, b


def ground(x: int) -> int:
    """`200`'s ground: flat at 250 to x 300, then up 100 over 300."""
    return 250 if x <= 300 else round(250 - (x - 300) / 3)


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


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ({"fill": (-0.1, 0.5)}, "fill must be"),
        ({"fill": (0.8, 0.2)}, "fill must be"),
        ({"fill": (0.5, 1.5)}, "at most 1"),
        ({"wander": -1}, "wander"),
    ],
)
def test_fill_is_an_ordered_share_and_wander_not_negative(
    cat: Catalogue, given: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compose_scene(cat, FIELD, rng(), client=CLIENT, **given)  # type: ignore[arg-type]


# --- the view ----------------------------------------------------------------


def test_draw_camera_never_leaves_the_vr_bounds_and_reaches_both_edges() -> None:
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


def test_the_scene_camera_stays_in_the_vr_bounds(cat: Catalogue) -> None:
    data = cat.map(FIELD)
    found = spots(data, compose._species(cat, data))
    generator = rng()

    cameras = [scene_camera(data, found, CLIENT, generator) for _ in range(300)]

    assert all(0 <= c.left and c.left + 200 <= 600 for c in cameras)
    assert all(0 <= c.top and c.top + 100 <= 300 for c in cameras)
    assert len({c.left for c in cameras}) > 50


def test_the_scene_camera_follows_a_character_on_a_spot(
    cat: Catalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no lag, the centre is 60 above the ground under it."""
    monkeypatch.setattr(compose, "CAMERA_LAG", (0, 0))
    data = cat.map(FIELD)
    found = spots(data, compose._species(cat, data))
    generator = rng()

    unclamped = 0
    for _ in range(200):
        camera = scene_camera(data, found, CLIENT, generator)
        x, y = camera.centre
        if 100 < x < 500 and 50 < y < 250:
            unclamped += 1
            assert y == ground(x) - compose.CAMERA_ABOVE_FEET
            assert any(spot.left <= x <= spot.right for spot in found)

    assert unclamped > 100


def test_a_map_with_no_spot_draws_its_camera_anywhere_in_its_bounds(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    spy = mocker.spy(compose, "draw_camera")

    compose_scene(cat, SMALL, rng(), client=CLIENT)

    assert spy.call_count == 1


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

    view = compose_scene(cat, FIELD, rng(), client=CLIENT, fill=EMPTY).image

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
        compose_scene(cat, FIELD, generator, client=CLIENT, fill=EMPTY)

    assert spy.call_count == 5


def test_cameras_n_renders_n_cameras_once_and_each_scene_picks_one(
    cat: Catalogue, drawn: Drawn, mocker: MockerFixture
) -> None:
    spy = mocker.spy(compose, "render_map")
    generator = rng()

    views = [
        compose_scene(cat, FIELD, generator, client=CLIENT, fill=EMPTY, cameras=3)
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

    def compose_one(fill: tuple[float, float]) -> np.ndarray:
        return compose_scene(
            cat, FIELD, generator, client=(600, 300), fill=fill, cameras=1
        ).image

    empty = compose_one(EMPTY)
    crowded = compose_one(FULL)

    assert not np.array_equal(crowded, empty)
    assert np.array_equal(compose_one(EMPTY), empty)


def test_cameras_must_be_positive(cat: Catalogue) -> None:
    with pytest.raises(ValueError, match="cameras"):
        compose_scene(cat, FIELD, rng(), client=CLIENT, cameras=0)


# --- the mobs ----------------------------------------------------------------


def test_spots_are_each_spawns_chain_inside_its_range(cat: Catalogue) -> None:
    """The Block's `[20, 500]` runs over footholds 1 and 2 (0 to 600)."""
    data = cat.map(FIELD)
    found = {
        s.spawn.id: (s.left, s.right) for s in spots(data, compose._species(cat, data))
    }

    assert found == {BLOCK: (20, 500), BAT: (100, 200), CRAB: (400, 500)}


def test_a_fill_share_of_the_spawn_points_have_a_mob_never_more(
    cat: Catalogue, drawn: Drawn
) -> None:
    counts: list[int] = []
    generator = rng()
    for _ in range(60):
        before = len(drawn.placements)
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=(0.0, 1.0))
        counts.append(len(drawn.placements) - before)

    assert set(counts) == {0, 1, 2, 3}


def test_a_full_map_has_one_mob_per_spawn_point(cat: Catalogue, drawn: Drawn) -> None:
    generator = rng()
    for _ in range(10):
        before = len(drawn.placements)
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL)
        ids = sorted(p.mob.id for p in drawn.placements[before:])
        assert ids == sorted([BLOCK, BAT, CRAB])


def test_a_mob_wanders_near_its_spawn_point(cat: Catalogue, drawn: Drawn) -> None:
    """The Block spawns at x 50, the Crab at 450."""
    generator = rng()
    for _ in range(30):
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL, wander=10)

    blocks = [p.x for p in drawn.placements if p.mob.id == BLOCK]
    crabs = [p.x for p in drawn.placements if p.mob.id == CRAB]
    assert all(40 <= x <= 60 for x in blocks)
    assert all(440 <= x <= 460 for x in crabs)
    assert len(set(blocks)) > 5


def test_mobs_stand_on_their_chain_and_never_leave_their_spot(
    cat: Catalogue, drawn: Drawn
) -> None:
    """The Block's spot runs off foothold 1 onto 2, which climbs 100 in 300."""
    generator = rng()
    for _ in range(60):
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL, wander=600)

    blocks = [p for p in drawn.placements if p.mob.id == BLOCK]
    # The view is the whole map, so view pixels are virtual coordinates.
    for block in blocks:
        assert 20 <= block.x <= 500
        assert block.y == ground(block.x)
    # A wander past the spot is clamped onto its ends.
    assert {20, 500} <= {b.x for b in blocks}
    crabs = [p for p in drawn.placements if p.mob.id == CRAB]
    assert all(400 <= c.x <= 500 for c in crabs)


def test_the_population_is_map_wide_and_the_camera_crops_it(
    cat: Catalogue, drawn: Drawn, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The view is columns 0 to 199: the Crab, at 400 to 500, is out of it."""
    fix_camera(monkeypatch, Camera(0, 200, 200, 100))

    scene = compose_scene(cat, FIELD, rng(), client=CLIENT, fill=FULL, wander=0)

    assert CRAB in {p.mob.id for p in drawn.placements}
    assert "Crab" not in {label.cls for label in scene.labels}
    assert "Block" in {label.cls for label in scene.labels}


def test_a_flying_mob_is_raised_up_to_150_px_within_the_view(
    cat: Catalogue, drawn: Drawn
) -> None:
    generator = rng()
    for _ in range(60):
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL)

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
    for _ in range(40):
        compose_scene(cat, FIELD, generator, client=CLIENT, fill=FULL)

    bats = [p for p in drawn.placements if p.mob.id == BAT]
    assert bats
    assert all(p.y >= 0 for p in bats)
    assert any(p.y == 0 for p in bats)


def test_a_mobs_action_frame_and_facing_are_drawn_among_those_it_has(
    cat: Catalogue, drawn: Drawn
) -> None:
    """The Block has `stand` of two frames, `move`, and `attack1`, never drawn."""
    generator = rng()
    for _ in range(60):
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL)

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
    for _ in range(30):
        before = len(drawn.placements)
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL)
        orders.add(tuple(p.mob.id for p in drawn.placements[before:]))

    assert len(orders) > 3


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

    scene = compose_scene(cat, FIELD, rng(), client=CLIENT)

    assert scene.labels == (Label("Block", (47, 40, 57, 50), 1.0),)
    assert at(scene.image, 46, 45) == rgb(BLUE)

    lowered = compose_scene(cat, FIELD, rng(), client=CLIENT, visibility_floor=0.1)
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
            compose_scene(cat, FIELD, rng(seed), client=(600, 300), fill=FULL)

    assert GHOST not in {p.mob.id for p in drawn.placements}
    assert any(
        "Ghost" in r.getMessage() and str(GHOST) in r.getMessage()
        for r in caplog.records
    )


# --- occluders ---------------------------------------------------------------


def calls(spy: MockType) -> list[tuple[int, int]]:
    """The `(x, y)` each call of a spied `drop` or `damage` was given."""
    found: list[tuple[int, int]] = []
    for call in spy.call_args_list:
        found.append((call.args[-3], call.args[-2]))
    return found


def every_site(*pool: str, per_site: tuple[int, int] = (1, 1)) -> Drops:
    """A drop site per mob shown, of `per_site` drops of the pool, equally weighed."""
    return Drops({key: 1.0 for key in pool}, (1.0, 1.0), per_site)


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: Drops({}), "at least one drop"),
        (lambda: Drops({"potion:1": 1.0}), "'meso:<id>' or 'item:<id>'"),
        (lambda: Drops({MESO: 0.0}), "more than 0"),
        (lambda: Drops({MESO: 1.0}, sites_per_mob=(1.0, 0.5)), "sites_per_mob"),
        (lambda: Drops({MESO: 1.0}, per_site=(-1, 2)), "per_site"),
        (lambda: Drops({MESO: 1.0}, spread=-1), "spread"),
        (lambda: Damage(count=(3, 1)), "count"),
        (lambda: Damage(values=(0, 10)), "start at 1"),
        (lambda: Damage(sets=()), "at least one digit set"),
    ],
)
def test_drops_and_damage_are_checked_when_made(
    make: Callable[[], object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make()


@pytest.mark.parametrize(
    ("given", "message"),
    [
        ({"drops": Drops({"item:12345": 1.0})}, "no sprite for drop 'item:12345'"),
        ({"drops": Drops({"meso:9000004": 1.0})}, "no sprite for drop 'meso:9000004'"),
        ({"damage": Damage()}, "no digit set 'NoCri0'"),
        ({"damage": Damage(sets=("NoRed1",))}, "even number"),
    ],
)
def test_a_drop_or_digit_set_the_catalogue_lacks_is_refused(
    cat: Catalogue, given: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        compose_scene(cat, FIELD, rng(), client=CLIENT, **given)  # type: ignore[arg-type]


def test_no_occluders_are_drawn_unless_asked_for(
    cat: Catalogue, drawn: Drawn, mocker: MockerFixture
) -> None:
    drops = mocker.spy(occluders, "drop")
    damage = mocker.spy(occluders, "damage")

    for seed in range(5):
        compose_scene(cat, FIELD, rng(seed), client=(600, 300), fill=FULL)

    assert drops.call_count == damage.call_count == 0
    assert drawn.overlays == []


def test_kill_sites_scale_with_the_mobs_shown(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    """The view is the whole map: a full map shows its 3 mobs."""
    spy = mocker.spy(occluders, "drop")
    generator = rng()

    compose_scene(
        cat, FIELD, generator, client=(600, 300), fill=FULL, drops=every_site(MESO)
    )
    assert spy.call_count == 3

    compose_scene(
        cat, FIELD, generator, client=(600, 300), fill=EMPTY, drops=every_site(MESO)
    )
    assert spy.call_count == 3


def test_a_sites_drops_fan_out_spread_apart_on_its_ground(
    cat: Catalogue, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(occluders, "DROP_JITTER", 0)
    spy = mocker.spy(occluders, "drop")
    drops = Drops({MESO: 1.0}, (1 / 3, 1 / 3), (3, 3), spread=24)
    generator = rng()

    fans: list[list[tuple[int, int]]] = []
    for _ in range(30):
        before = spy.call_count
        compose_scene(cat, FIELD, generator, client=(600, 300), fill=FULL, drops=drops)
        fans.append(calls(spy)[before:])

    steps: list[list[int]] = []
    for fan in fans:
        assert len(fan) == 3
        for x, y in fan:
            assert y == ground(x)
        steps.append([b - a for a, b in itertools.pairwise(x for x, _ in fan)])
    # 24 apart, unless a spot's end clamps the fan closer.
    assert all(0 <= step <= 24 for pair in steps for step in pair)
    assert steps.count([24, 24]) > len(steps) // 2


def test_drops_lie_on_spots_overlapping_the_view(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    """The view is the whole map; spots run over `[20, 500]`."""
    spy = mocker.spy(occluders, "drop")
    generator = rng()
    for _ in range(30):
        compose_scene(
            cat,
            FIELD,
            generator,
            client=(600, 300),
            fill=FULL,
            drops=every_site(MESO, per_site=(2, 2)),
        )

    points = calls(spy)
    assert len(points) == 180
    for x, y in points:
        assert 20 <= x <= 500
        assert y == ground(x)
    assert min(x for x, _ in points) < 100
    assert max(x for x, _ in points) > 400


def test_drops_come_only_from_the_pool_by_weight(cat: Catalogue) -> None:
    sprites = occluders.Sprites.read(cat)
    images = Images(cat.store.images)
    generator = rng()

    green = sprites.pool(Drops({GREEN_ITEM: 1.0}))
    mixed = sprites.pool(Drops({GREEN_ITEM: 3.0, MESO: 1.0}))
    only_green = [occluders.drop(green, images, 100, 80, generator) for _ in range(30)]
    both = [occluders.drop(mixed, images, 100, 80, generator) for _ in range(400)]

    assert {d.pixels.shape[:2] for d in only_green} == {(8, 8)}
    shapes = [(d.pixels.shape[1], d.pixels.shape[0]) for d in both]
    assert set(shapes) == {(8, 8), (6, 6), (2, 6)}
    assert shapes.count((8, 8)) / len(shapes) == pytest.approx(0.75, abs=0.07)
    # Centred on x, the bottom on the ground: (-12, 8) in a 32-pixel slot.
    icon = only_green[0]
    assert (icon.left, icon.top) == (96, 72)


def test_a_cash_item_drops_when_the_pool_names_it(cat: Catalogue) -> None:
    sprites = occluders.Sprites.read(cat)

    ((frames, weight),) = sprites.pool(Drops({"item:5010000": 2.0}))

    assert len(frames) == 1
    assert weight == 2.0


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
            cat, FIELD, rng(seed), client=CLIENT, drops=every_site(GREEN_ITEM)
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

    compose_scene(
        cat, FIELD, rng(), client=CLIENT, damage=Damage((3, 3), sets=RED_ONLY)
    )

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

    compose_scene(
        cat, FIELD, rng(), client=CLIENT, damage=Damage((1, 1), sets=RED_ONLY)
    )

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
            cat, FIELD, rng(seed), client=CLIENT, damage=Damage((4, 4), sets=RED_ONLY)
        )

    assert calls(spy) == [(101, 76)] * 20


def test_damage_numbers_need_a_drawn_mob(cat: Catalogue, mocker: MockerFixture) -> None:
    spy = mocker.spy(occluders, "damage")

    compose_scene(
        cat,
        FIELD,
        rng(),
        client=CLIENT,
        fill=EMPTY,
        damage=Damage((3, 3), sets=RED_ONLY),
    )

    assert spy.call_count == 0


def test_a_damage_number_is_its_value_a_large_first_digit_then_small_ones(
    cat: Catalogue,
) -> None:
    """`NoRed1`'s digits are 16x14, `NoRed0`'s 12x10; they overlap by 8."""
    sprites = occluders.Sprites.read(cat)
    pairs = sprites.pairs(Damage(sets=RED_ONLY))
    images = Images(cat.store.images)
    generator = rng()
    lengths: set[int] = set()
    rises: set[int] = set()
    for _ in range(200):
        number = occluders.damage(pairs, (50, 350), images, 100, 80, generator)
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

    # 50 to 350: two or three digits, never one or four.
    assert lengths == {2, 3}
    assert min(rises) >= 0
    assert max(rises) <= occluders.DAMAGE_RISE
    assert len(rises) > 30


def test_digit_sets_are_kept_by_name_and_one_short_of_a_digit_is_left_out(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    full = cat.damage_digits()
    sprites = occluders.Sprites.read(cat)
    assert set(sprites.digits) == {"NoRed0", "NoRed1"}
    ((rest, first),) = sprites.pairs(Damage(sets=RED_ONLY))
    assert sorted(rest) == sorted(first) == list(range(10))

    mocker.patch.object(
        cat, "damage_digits", return_value=tuple(d for d in full if d.digit != 7)
    )
    assert occluders.Sprites.read(cat).digits == {}


def test_the_same_seed_gives_the_same_occluded_scene(
    cat: Catalogue, mocker: MockerFixture
) -> None:
    spy = mocker.spy(occluders, "drop")
    drops = Drops({GREEN_ITEM: 1.0, MESO: 1.0}, (1.0, 2.0), (1, 3))
    damage = Damage((0, 5), (1, 999), RED_ONLY)

    def scenes(seed: int) -> list[tuple[bytes, tuple[Label, ...]]]:
        generator = rng(seed)
        return [
            (scene.image.tobytes(), scene.labels)
            for scene in (
                compose_scene(
                    cat, FIELD, generator, client=CLIENT, drops=drops, damage=damage
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
                    cat, FIELD, generator, client=CLIENT, fill=FULL, cameras=cameras
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
