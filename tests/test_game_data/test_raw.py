"""
The raw layer's pieces that need no client: a tree as JSON, the PNG writer,
the image store, and the build id.
"""

import json
import os
from pathlib import Path
from types import MappingProxyType

import cv2
import numpy as np
import pytest

from game_data.archive import (
    CanvasNode,
    CanvasRef,
    ConvexNode,
    DoubleNode,
    FloatNode,
    IntNode,
    LongNode,
    Node,
    NullNode,
    PropertyNode,
    RawDataNode,
    RawDataRef,
    ShortNode,
    SoundNode,
    SoundRef,
    StringNode,
    UolNode,
    VectorNode,
)
from game_data.extraction import (
    CanvasImage,
    HashedArchive,
    ImageStore,
    Json,
    UnstorableNode,
    build_id,
    encode_tree,
    pixel_hash,
    png,
)
from game_data.extraction.raw import dumps


def prop(name: str, *children: Node) -> PropertyNode:
    return PropertyNode(name=name, children=_children(children))


def _children(children: tuple[Node, ...]) -> MappingProxyType[str, Node]:
    return MappingProxyType({child.name: child for child in children})


def canvas(name: str, *children: Node, width: int = 1, height: int = 1) -> CanvasNode:
    ref = CanvasRef(offset=0, length=0, format=2, scale=0, width=width, height=height)
    return CanvasNode(name=name, canvas=ref, children=_children(children))


def encode(tree: PropertyNode) -> dict[str, Json]:
    return encode_tree(
        tree,
        canvas=lambda path, node: CanvasImage(f"image of {path}", 3, 4),
        payload_sha256=lambda offset, length: f"sha of {offset}+{length}",
    )


def test_every_node_type_encodes_as_documented() -> None:
    sound = SoundRef(
        offset=10, length=20, duration_ms=1500, header_offset=0, header_length=0
    )
    tree = prop(
        "",
        NullNode(name="null"),
        ShortNode(name="short", value=-2),
        IntNode(name="int", value=5),
        LongNode(name="long", value=2**40),
        FloatNode(name="float", value=0.5),
        DoubleNode(name="double", value=5.0),
        StringNode(name="string", value="Henesys"),
        prop("sub", IntNode(name="x", value=1)),
        VectorNode(name="origin", x=1, y=-2),
        UolNode(name="link", path="../0"),
        canvas("0", IntNode(name="delay", value=90)),
        ConvexNode(
            name="convex", children=_children((VectorNode(name="0", x=1, y=2),))
        ),
        SoundNode(name="bgm", sound=sound),
        RawDataNode(
            name="raw",
            data=RawDataRef(offset=30, length=40),
            children=_children((IntNode(name="w", value=7),)),
        ),
    )

    assert encode(tree) == {
        "null": None,
        "short": {"$type": "short", "value": -2},
        "int": 5,
        "long": {"$type": "long", "value": 2**40},
        "float": {"$type": "float", "value": 0.5},
        "double": 5.0,
        "string": "Henesys",
        "sub": {"x": 1},
        "origin": {"$type": "vector", "x": 1, "y": -2},
        "link": {"$type": "uol", "path": "../0"},
        "0": {"$type": "canvas", "image": "image of 0", "w": 3, "h": 4, "delay": 90},
        "convex": {"$type": "convex", "0": {"$type": "vector", "x": 1, "y": 2}},
        "bgm": {
            "$type": "sound",
            "duration_ms": 1500,
            "length": 20,
            "sha256": "sha of 10+20",
        },
        "raw": {"$type": "raw_data", "length": 40, "sha256": "sha of 30+40", "w": 7},
    }


def test_the_stored_text_keeps_ints_and_doubles_apart_and_the_childrens_order() -> None:
    tree = prop(
        "", IntNode(name="b", value=1), DoubleNode(name="a", value=1.0), prop("c")
    )

    text = dumps(encode(tree))

    assert text == '{"b":1,"a":1.0,"c":{}}'
    loaded = json.loads(text)
    assert type(loaded["b"]) is int
    assert type(loaded["a"]) is float


def test_a_canvas_path_reaches_the_canvas_callback() -> None:
    seen: list[str] = []
    tree = prop("", prop("stand", canvas("0")))

    encode_tree(
        tree,
        canvas=lambda path, node: seen.append(path) or CanvasImage(None, 1, 1),
        payload_sha256=lambda offset, length: "",
    )

    assert seen == ["stand/0"]


@pytest.mark.parametrize(
    "tree",
    [
        prop("", prop("a", IntNode(name="$type", value=1))),
        prop("", canvas("0", IntNode(name="w", value=1))),
        prop("", canvas("0", StringNode(name="image", value="x"))),
    ],
    ids=["$type in a property", "w in a canvas", "image in a canvas"],
)
def test_a_reserved_child_name_raises_naming_the_node(tree: PropertyNode) -> None:
    with pytest.raises(UnstorableNode, match="is reserved"):
        encode(tree)


def rgba(height: int, width: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        0, 256, (height, width, 4), dtype=np.uint8
    )


def test_a_png_reads_back_as_its_pixels(tmp_path: Path) -> None:
    pixels = rgba(3, 5)
    file = tmp_path / "image.png"
    file.write_bytes(png(pixels))

    read = cv2.imread(str(file), cv2.IMREAD_UNCHANGED)

    assert read is not None
    np.testing.assert_array_equal(cv2.cvtColor(read, cv2.COLOR_BGRA2RGBA), pixels)


def test_the_same_bytes_in_another_shape_get_another_name() -> None:
    pixels = rgba(2, 3)

    assert pixel_hash(pixels) != pixel_hash(pixels.reshape(3, 2, 4))
    assert pixel_hash(pixels) == pixel_hash(pixels.copy())


def test_an_image_already_in_the_store_isnt_rewritten(tmp_path: Path) -> None:
    store = ImageStore(tmp_path / "images")
    name = "ab" * 32
    assert store.write(name, rgba(1, 1, seed=1))
    before = store.path(name).read_bytes()
    os.utime(store.path(name), ns=(10**18, 10**18))

    assert not store.write(name, rgba(1, 1, seed=2))

    assert store.path(name) == tmp_path / "images" / "ab" / f"{name}.png"
    assert store.path(name).read_bytes() == before
    assert store.path(name).stat().st_mtime_ns == 10**18


def test_the_build_id_depends_on_paths_sizes_and_contents_only() -> None:
    a = HashedArchive("Map/Map.wz", 10, 111, "aa")
    b = HashedArchive("Mob/Mob.wz", 20, 222, "bb")

    assert build_id([a, b]) == build_id([b, a])
    assert build_id([a, b]) == build_id([HashedArchive("Map/Map.wz", 10, 999, "aa"), b])
    assert build_id([a, b]) != build_id([HashedArchive("Map/Map.wz", 10, 111, "ab"), b])
    assert build_id([a, b]) != build_id([a])
    assert len(build_id([a])) == 16
