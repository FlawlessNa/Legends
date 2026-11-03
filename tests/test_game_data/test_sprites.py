"""
`Sprites` on a synthetic store: a hand-built `raw.sqlite`, with the PNGs and
blobs written by the test, in a temporary root.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture

from game_data.catalogue import CatalogueError
from game_data.catalogue.trees import Tree
from game_data.extraction import ImageStore, Manifest, Store
from game_data.sprites import Sprite, SpriteNotFound, Sprites

BUILD = "0123456789abcdef"
FONT = b"not really a font" * 3
FONT_SHA = hashlib.sha256(FONT).hexdigest()
DIGIT = np.arange(5 * 7 * 4, dtype=np.uint8).reshape(7, 5, 4)
DIGIT_NAME = "aa" * 32
USER = np.full((2, 3, 4), 200, dtype=np.uint8)
USER_NAME = "bb" * 32


def canvas(name: str | None, w: int, h: int, **children: object) -> dict[str, Any]:
    return {"$type": "canvas", "image": name, "w": w, "h": h, **children}


def vector(x: int, y: int) -> dict[str, Any]:
    return {"$type": "vector", "x": x, "y": y}


STATUS_BAR = {
    "canvas:gaugeLabel": canvas(DIGIT_NAME, 5, 7),
    "gauge": {
        "number": {
            "0": canvas(DIGIT_NAME, 5, 7, origin=vector(1, 2), z=0),
            "1": {"$type": "uol", "path": "0"},
            "2": canvas(None, 1, 1, _outlink="Nowhere/x.img/y"),
            "elsewhere": {"$type": "uol", "path": "../vector:posNumberHp"},
            "gone": {"$type": "uol", "path": "../nothing"},
        },
        "vector:posNumberHp": vector(-7, 9),
    },
    "text": "hello",
}
MAP_HELPER = {"minimap": {"user": canvas(USER_NAME, 3, 2, origin=vector(6, 6))}}
FONT_IMAGE = {
    "FONT_DATA": {"$type": "raw_data", "length": len(FONT), "sha256": FONT_SHA}
}


def build_store(root: Path) -> Store:
    store = Store(root)
    folder = store.extraction(BUILD)
    folder.mkdir(parents=True)
    Manifest(
        build=BUILD,
        extractor_version=1,
        catalogue_schema_version=None,
        extracted_at=datetime(2026, 10, 31, tzinfo=UTC),
        archives=(),
        images=3,
        canvases=4,
        failures=(),
    ).write(folder)
    with closing(sqlite3.connect(folder / "raw.sqlite")) as db:
        db.execute(
            "CREATE TABLE images (path TEXT PRIMARY KEY, sha256 TEXT, tree TEXT)"
        )
        for path, tree in {
            "UI/StatusBar.img": STATUS_BAR,
            "Map/MapHelper.img": MAP_HELPER,
            "UI/Font/Noto.img": FONT_IMAGE,
        }.items():
            db.execute("INSERT INTO images VALUES (?, '', ?)", (path, json.dumps(tree)))
        db.commit()
    store.images.write(DIGIT_NAME, DIGIT)
    store.images.write(USER_NAME, USER)
    store.blobs.write(FONT)
    return store


@pytest.fixture
def root(tmp_path: Path) -> Path:
    build_store(tmp_path / "store")
    return tmp_path / "store"


@pytest.fixture
def sprites(root: Path) -> Iterator[Sprites]:
    with Sprites.latest(root) as found:
        yield found


def test_latest_and_open_are_context_managers_on_an_extraction(root: Path) -> None:
    with Sprites.latest(root) as latest:
        assert latest.build == BUILD
    with Sprites.open(BUILD, root=root) as opened:
        assert opened.canvas("UI/StatusBar.img/canvas:gaugeLabel").rgba.shape == (
            7,
            5,
            4,
        )
    with pytest.raises(sqlite3.ProgrammingError):
        latest.children("UI/StatusBar.img")


def test_a_store_without_the_build_is_a_catalogue_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="no extraction"):
        Sprites.latest(tmp_path)
    with pytest.raises(CatalogueError, match="no extraction ffff"):
        Sprites.open("ffff", tmp_path)


def test_a_canvas_is_its_pixels_in_rgba_order_and_its_origin(sprites: Sprites) -> None:
    sprite = sprites.canvas("UI/StatusBar.img/gauge/number/0")

    assert isinstance(sprite, Sprite)
    assert sprite.path == "UI/StatusBar.img/gauge/number/0"
    assert sprite.rgba.dtype == np.uint8
    assert np.array_equal(sprite.rgba, DIGIT)
    assert sprite.origin == (1, 2)
    assert not sprite.rgba.flags.writeable


def test_a_canvas_without_an_origin_has_the_origin_zero(sprites: Sprites) -> None:
    assert sprites.canvas("UI/StatusBar.img/canvas:gaugeLabel").origin == (0, 0)


def test_node_names_keep_their_type_prefixes_and_images_nest_in_directories(
    sprites: Sprites,
) -> None:
    assert sprites.canvas("Map/MapHelper.img/minimap/user").origin == (6, 6)
    assert sprites.vector("UI/StatusBar.img/gauge/vector:posNumberHp") == (-7, 9)


def test_children_are_in_the_clients_order_and_include_a_canvas_own_properties(
    sprites: Sprites,
) -> None:
    assert sprites.children("UI/StatusBar.img") == [
        "canvas:gaugeLabel",
        "gauge",
        "text",
    ]
    assert sprites.children("UI/StatusBar.img/gauge/number")[:2] == ["0", "1"]
    assert sprites.children("UI/StatusBar.img/gauge/number/0") == ["origin", "z"]


def test_a_uol_is_followed_on_the_way_and_at_the_end(sprites: Sprites) -> None:
    linked = sprites.canvas("UI/StatusBar.img/gauge/number/1")
    assert np.array_equal(linked.rgba, DIGIT)
    assert linked.origin == (1, 2)
    assert sprites.vector("UI/StatusBar.img/gauge/number/elsewhere") == (-7, 9)
    assert sprites.children("UI/StatusBar.img/gauge/number/1")[0] == "origin"


def test_each_image_tree_is_parsed_once_per_instance(
    root: Path, mocker: MockerFixture
) -> None:
    loads = mocker.spy(Tree, "of")
    with Sprites.latest(root) as sprites:
        sprites.canvas("UI/StatusBar.img/gauge/number/0")
        sprites.vector("UI/StatusBar.img/gauge/vector:posNumberHp")
        sprites.children("UI/StatusBar.img")
        sprites.canvas("Map/MapHelper.img/minimap/user")
        assert loads.call_count == 2
    with Sprites.latest(root) as other:
        other.children("UI/StatusBar.img")
    assert loads.call_count == 3


@pytest.mark.parametrize(
    ("call", "path", "reason"),
    [
        ("canvas", "UI/Nope.img/canvas:gaugeLabel", "no image UI/Nope.img"),
        ("canvas", "UI/StatusBar.img/nope", "no node at 'nope'"),
        ("canvas", "UI/StatusBar.img/gauge/nope/0", "no node at 'nope'"),
        ("canvas", "UI/StatusBar", "names no image"),
        ("canvas", "UI/StatusBar.img/gauge/vector:posNumberHp", "not a canvas"),
        ("canvas", "UI/StatusBar.img/text", "not a canvas"),
        ("canvas", "UI/StatusBar.img", "not a canvas"),
        ("canvas", "UI/StatusBar.img/gauge/number/2", "image is null"),
        ("canvas", "UI/StatusBar.img/gauge/number/gone", "names nothing"),
        ("vector", "UI/StatusBar.img/canvas:gaugeLabel", "not a vector"),
        ("vector", "UI/StatusBar.img/gauge/nope", "no node at 'nope'"),
        ("children", "UI/StatusBar.img/text", "no children"),
        ("children", "UI/Nope.img", "no image UI/Nope.img"),
        ("raw_data", "UI/StatusBar.img/text", "not a raw_data"),
        ("raw_data", "UI/Font/Nope.img/FONT_DATA", "no image UI/Font/Nope.img"),
    ],
)
def test_a_path_that_names_nothing_usable_raises_sprite_not_found_naming_it(
    sprites: Sprites, call: str, path: str, reason: str
) -> None:
    with pytest.raises(SpriteNotFound) as error:
        getattr(sprites, call)(path)

    assert path in str(error.value)
    assert reason in str(error.value)


def test_a_canvas_whose_png_is_missing_is_sprite_not_found(
    root: Path, sprites: Sprites
) -> None:
    ImageStore(root / "images").path(DIGIT_NAME).unlink()

    with pytest.raises(SpriteNotFound, match="can't be read"):
        sprites.canvas("UI/StatusBar.img/canvas:gaugeLabel")


def test_raw_data_is_the_blob_read_back(sprites: Sprites) -> None:
    assert sprites.raw_data("UI/Font/Noto.img/FONT_DATA") == FONT


def test_raw_data_checks_the_blobs_sha256(root: Path, sprites: Sprites) -> None:
    Store(root).blobs.path(FONT_SHA).write_bytes(b"tampered")

    with pytest.raises(CatalogueError, match="SHA-256"):
        sprites.raw_data("UI/Font/Noto.img/FONT_DATA")


def test_raw_data_without_its_blob_says_to_extract(
    root: Path, sprites: Sprites
) -> None:
    Store(root).blobs.path(FONT_SHA).unlink()

    with pytest.raises(CatalogueError, match="no blob .*extract"):
        sprites.raw_data("UI/Font/Noto.img/FONT_DATA")
