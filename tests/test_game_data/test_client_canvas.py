"""
`ClientData.canvas`: a canvas's pixels, wherever the client keeps them.

The fixture client has a data tree and its `_Canvas` sibling, as Classic does:

    Data/
      Mob/            Mob.wz: 0100100.img, and an empty _Canvas directory
        _Canvas/      _Canvas.wz: 0100100.img, shared.img
      Packs/          Mob_00000.ms: Mob/0100200.img

The data side's canvases are 1x1 magenta placeholders, so a test fails if the
placeholder comes back instead of the pixels a link leads to. In the real
client, a pack's canvases mostly hold their own pixels, and link with `_inlink`.
"""

import random
import zlib
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from game_data.archive import (
    BrokenLink,
    ClientData,
    CorruptArchive,
    IntNode,
    NodeNotFound,
    StringNode,
    VectorNode,
)
from tests.test_game_data import wz_writer as w

MAGENTA = (255, 0, 255, 255)
STAND = [(1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16)]
SHARED = [(200, 100, 50, 255), (0, 0, 0, 0)]
OWN = [(10, 20, 30, 40), (50, 60, 70, 80)]


def bgra(pixels: list[tuple[int, int, int, int]]) -> bytes:
    return zlib.compress(b"".join(bytes([b, g, r, a]) for r, g, b, a in pixels))


def placeholder(name: str, *children: w.Property) -> w.Canvas:
    return w.Canvas(name, 1, 1, bgra([MAGENTA]), format=2, children=children)


FRAME_PROPERTIES: list[w.Property] = [
    w.Vector("origin", 20, 40),
    w.Int("delay", 180),
    w.Vector("lt", -20, -40),
    w.Vector("rb", 20, 0),
    w.String("_hash", "ab" * 32),
]

DATA_IMAGE: list[w.Property] = [
    w.Prop(
        "stand",
        [
            placeholder(
                "0",
                *FRAME_PROPERTIES,
                w.String("_outlink", "Mob/_Canvas/0100100.img/stand/0"),
            ),
            placeholder(
                "1",
                w.Int("delay", 90),
                w.String("_outlink", "Mob/_Canvas/shared.img/frame"),
            ),
            w.Uol("2", "0"),
            w.Canvas("3", 2, 1, bgra(OWN), format=2, children=[w.Int("delay", 60)]),
            placeholder("4", w.Vector("origin", 1, 2), w.String("_inlink", "stand/0")),
        ],
    ),
    w.Prop(
        "bad",
        [
            placeholder("dangling", w.String("_outlink", "Mob/_Canvas/0100100.img/x")),
            placeholder(
                "both",
                w.String("_outlink", "Mob/_Canvas/0100100.img/stand/0"),
                w.String("_inlink", "stand/0"),
            ),
            placeholder("number", w.Int("_outlink", 7)),
            placeholder(
                "property", w.String("_outlink", "Mob/_Canvas/0100100.img/stand")
            ),
            placeholder("loop a", w.String("_inlink", "bad/loop b")),
            placeholder("loop b", w.String("_inlink", "bad/loop a")),
            w.Int("delay", 100),
        ],
    ),
]


# Noise, so that it compresses to more than the 1024 bytes a pack encrypts.
_RANDOM = random.Random(0)
NOISE: list[tuple[int, int, int, int]] = [
    (r, g, b, a) for r, g, b, a in (_RANDOM.randbytes(4) for _ in range(600))
]

PACK_IMAGE: list[w.Property] = [
    w.Prop(
        "stand",
        [
            w.Canvas("0", 2, 1, bgra(OWN), format=2, children=[w.Int("delay", 60)]),
            w.Canvas("noise", 600, 1, bgra(NOISE), format=2),
            w.Canvas("1", 1, 2, bgra(SHARED), format=2),
            placeholder("2", w.String("_inlink", "stand/1")),
            placeholder("3", w.String("_outlink", "Mob/_Canvas/shared.img/frame")),
        ],
    )
]


@pytest.fixture
def client(tmp_path: Path) -> ClientData:
    data = tmp_path / "Data"
    w.write_tree(
        data / "Mob", [w.Dir("_Canvas"), w.Img("0100100.img", DATA_IMAGE)], ini=False
    )
    w.write_tree(
        data / "Mob" / "_Canvas",
        [
            w.Img(
                "0100100.img",
                [w.Prop("stand", [w.Canvas("0", 2, 2, bgra(STAND), format=2)])],
            ),
            w.Img("shared.img", [w.Canvas("frame", 1, 2, bgra(SHARED), format=2)]),
        ],
        ini=False,
    )
    w.write_pack(
        data / "Packs" / "Mob_00000.ms", [w.Img("Mob/0100200.img", PACK_IMAGE)]
    )
    return ClientData(data)


def rgba(pixels: list[tuple[int, int, int, int]], width: int) -> np.ndarray:
    return np.array(pixels, dtype=np.uint8).reshape(-1, width, 4)


def test_an_outlink_gives_the_canvas_archives_pixels_with_the_data_sides_properties(
    client: ClientData,
) -> None:
    canvas = client.canvas("Mob/0100100.img/stand/0")

    np.testing.assert_array_equal(canvas.pixels, rgba(STAND, 2))
    assert canvas.path == "Mob/0100100.img/stand/0"
    assert canvas.source == "Mob/_Canvas/0100100.img/stand/0"
    properties = canvas.properties
    assert properties["origin"] == VectorNode(name="origin", x=20, y=40)
    assert properties["delay"] == IntNode(name="delay", value=180)
    assert properties["lt"] == VectorNode(name="lt", x=-20, y=-40)
    assert properties["rb"] == VectorNode(name="rb", x=20, y=0)
    assert properties["_hash"] == StringNode(name="_hash", value="ab" * 32)


def test_an_outlink_may_name_another_image_and_path(client: ClientData) -> None:
    canvas = client.canvas("Mob/0100100.img/stand/1")

    np.testing.assert_array_equal(canvas.pixels, rgba(SHARED, 1))
    assert canvas.source == "Mob/_Canvas/shared.img/frame"
    assert canvas.properties["delay"] == IntNode(name="delay", value=90)


def test_a_canvas_without_a_link_holds_its_own_pixels(client: ClientData) -> None:
    canvas = client.canvas("Mob/0100100.img/stand/3")

    np.testing.assert_array_equal(canvas.pixels, rgba(OWN, 2))
    assert canvas.source == canvas.path == "Mob/0100100.img/stand/3"


def test_an_inlink_leads_within_the_image_and_on_through_its_targets_outlink(
    client: ClientData,
) -> None:
    canvas = client.canvas("Mob/0100100.img/stand/4")

    np.testing.assert_array_equal(canvas.pixels, rgba(STAND, 2))
    assert canvas.source == "Mob/_Canvas/0100100.img/stand/0"
    assert canvas.properties["origin"] == VectorNode(name="origin", x=1, y=2)
    assert "delay" not in canvas.properties


def test_a_uol_to_a_canvas_is_followed(client: ClientData) -> None:
    canvas = client.canvas("Mob/0100100.img/stand/2")

    assert canvas.path == "Mob/0100100.img/stand/0"
    np.testing.assert_array_equal(canvas.pixels, rgba(STAND, 2))


def test_a_path_to_something_other_than_a_canvas_raises(client: ClientData) -> None:
    with pytest.raises(NodeNotFound, match="it's a int, not a canvas"):
        client.canvas("Mob/0100100.img/bad/delay")


def test_a_link_naming_nothing_raises_naming_the_link(client: ClientData) -> None:
    with pytest.raises(BrokenLink) as raised:
        client.canvas("Mob/0100100.img/bad/dangling")

    error = raised.value
    assert error.archive.endswith("Mob.wz")
    assert (error.image, error.node) == ("0100100.img", "bad/dangling/_outlink")
    assert "names nothing" in error.reason


def test_a_path_naming_nothing_is_not_a_broken_link(client: ClientData) -> None:
    with pytest.raises(NodeNotFound) as raised:
        client.canvas("Mob/0100100.img/stand/nothing")

    assert not isinstance(raised.value, BrokenLink)


def test_canvas_source_finds_the_pixels_without_decoding_them(
    client: ClientData, mocker: MockerFixture
) -> None:
    decode = mocker.patch("game_data.archive.wz.decode_canvas")

    found = client.canvas_source("Mob/0100100.img/stand/4")

    decode.assert_not_called()
    assert found.path == "Mob/0100100.img/stand/4"
    assert found.source == "Mob/_Canvas/0100100.img/stand/0"
    assert found.image.path == "Mob/_Canvas/0100100.img"
    assert found.node == "stand/0"
    assert (found.ref.width, found.ref.height) == (2, 2)
    assert found.properties["origin"] == VectorNode(name="origin", x=1, y=2)


def test_a_canvas_sources_pixels_decode_to_the_canvas(client: ClientData) -> None:
    found = client.canvas_source("Mob/0100100.img/stand/1")

    np.testing.assert_array_equal(found.pixels(), rgba(SHARED, 1))


@pytest.mark.parametrize(
    ("node", "reason"),
    [
        ("bad/both", "it has both _outlink and _inlink"),
        ("bad/number", "it's a int, not a string"),
        ("bad/property", "but this is a property, not a canvas"),
        ("bad/loop a", "loop"),
    ],
)
def test_a_broken_link_raises(client: ClientData, node: str, reason: str) -> None:
    with pytest.raises(CorruptArchive, match=reason):
        client.canvas(f"Mob/0100100.img/{node}")


def test_a_pack_canvas_in_the_encrypted_start_decodes(client: ClientData) -> None:
    canvas = client.canvas("Mob/0100200.img/stand/0")

    np.testing.assert_array_equal(canvas.pixels, rgba(OWN, 2))
    assert canvas.properties["delay"] == IntNode(name="delay", value=60)


def test_a_pack_canvas_past_the_encrypted_start_decodes(client: ClientData) -> None:
    np.testing.assert_array_equal(
        client.canvas("Mob/0100200.img/stand/noise").pixels, rgba(NOISE, 600)
    )
    np.testing.assert_array_equal(
        client.canvas("Mob/0100200.img/stand/1").pixels, rgba(SHARED, 1)
    )


def test_a_pack_canvas_follows_its_links(client: ClientData) -> None:
    inlink = client.canvas("Mob/0100200.img/stand/2")
    outlink = client.canvas("Mob/0100200.img/stand/3")

    assert inlink.source == "Mob/0100200.img/stand/1"
    np.testing.assert_array_equal(inlink.pixels, rgba(SHARED, 1))
    assert outlink.source == "Mob/_Canvas/shared.img/frame"
    np.testing.assert_array_equal(outlink.pixels, rgba(SHARED, 1))
