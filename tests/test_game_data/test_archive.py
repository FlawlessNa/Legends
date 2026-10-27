"""
`game_data.archive` against synthetic archives from `wz_writer`.

No client data is read here: every archive is written by the test that reads it.
"""

from collections.abc import Sequence
from pathlib import Path

import pytest

from game_data.archive import (
    CanvasNode,
    CanvasRef,
    ConvexNode,
    CorruptArchive,
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
    WzArchive,
    parse_image,
)
from game_data.archive.wz import encrypted_version
from tests.test_game_data import wz_writer as w

PIXELS = bytes(range(40))
AUDIO = b"RIFF-not-really-audio" * 3
RAW = b"\x00\x01\x02raw bytes"

# One of every property type, nested, with strings repeated so that the writer
# emits offset string blocks as well as inline ones.
EVERY_TYPE: list[w.Property] = [
    w.Null("nothing"),
    w.Short("short", -12345),
    w.Int("small", 7),
    w.Int("int", 2_000_000_000),
    w.Int("int19", -300, code=19),
    w.Long("long", -(2**40)),
    w.Long("small long", 3),
    w.Float("float", 1.5),
    w.Float("zero", 0.0),
    w.Double("double", -2.25),
    w.String("string", "Henesys"),
    w.String("again", "Henesys"),
    w.String("unicode", "헤네시스"),
    w.String("long string", "x" * 300),
    w.String("empty", ""),
    w.Prop(
        "info",
        [
            w.Vector("origin", 12, -300),
            w.Uol("link", "../move/0"),
            w.Prop("move", [w.Int("0", 1)]),
            w.Prop("empty"),
        ],
    ),
    w.Canvas(
        "canvas",
        width=4,
        height=5,
        pixels=PIXELS,
        format=2,
        scale=1,
        children=[w.Vector("origin", 2, 3), w.Int("delay", 120)],
    ),
    w.Canvas("bare canvas", width=1, height=1, pixels=b"\x78\x9c"),
    w.Convex("convex", [(0, 0), (10, -5), (-200, 400)]),
    w.Sound("sound", audio=AUDIO, duration_ms=1500),
    w.RawData("raw", payload=RAW),
]


def _expected(layout: w.Layout, image: str) -> PropertyNode:
    def payload(path: str) -> tuple[int, int]:
        return layout.payloads[f"{image}/{path}"]

    canvas_at, canvas_length = payload("canvas")
    bare_at, bare_length = payload("bare canvas")
    sound_at, sound_length = payload("sound")
    header_at, header_length = payload("sound#header")
    raw_at, raw_length = payload("raw")
    children: list[Node] = [
        NullNode(name="nothing"),
        ShortNode(name="short", value=-12345),
        IntNode(name="small", value=7),
        IntNode(name="int", value=2_000_000_000),
        IntNode(name="int19", value=-300),
        LongNode(name="long", value=-(2**40)),
        LongNode(name="small long", value=3),
        FloatNode(name="float", value=1.5),
        FloatNode(name="zero", value=0.0),
        DoubleNode(name="double", value=-2.25),
        StringNode(name="string", value="Henesys"),
        StringNode(name="again", value="Henesys"),
        StringNode(name="unicode", value="헤네시스"),
        StringNode(name="long string", value="x" * 300),
        StringNode(name="empty", value=""),
        PropertyNode(
            name="info",
            children=_named(
                VectorNode(name="origin", x=12, y=-300),
                UolNode(name="link", path="../move/0"),
                PropertyNode(name="move", children=_named(IntNode(name="0", value=1))),
                PropertyNode(name="empty", children={}),
            ),
        ),
        CanvasNode(
            name="canvas",
            canvas=CanvasRef(
                offset=canvas_at,
                length=canvas_length,
                format=2,
                scale=1,
                width=4,
                height=5,
            ),
            children=_named(
                VectorNode(name="origin", x=2, y=3), IntNode(name="delay", value=120)
            ),
        ),
        CanvasNode(
            name="bare canvas",
            canvas=CanvasRef(
                offset=bare_at, length=bare_length, format=1, scale=0, width=1, height=1
            ),
            children={},
        ),
        ConvexNode(
            name="convex",
            children=_named(
                VectorNode(name="0", x=0, y=0),
                VectorNode(name="1", x=10, y=-5),
                VectorNode(name="2", x=-200, y=400),
            ),
        ),
        SoundNode(
            name="sound",
            sound=SoundRef(
                offset=sound_at,
                length=sound_length,
                duration_ms=1500,
                header_offset=header_at,
                header_length=header_length,
            ),
        ),
        RawDataNode(
            name="raw",
            data=RawDataRef(offset=raw_at, length=raw_length),
            children={},
        ),
    ]
    return PropertyNode(name="", children=_named(*children))


def _named(*nodes: Node) -> dict[str, Node]:
    return {node.name: node for node in nodes}


@pytest.fixture
def every_type(tmp_path: Path) -> tuple[Path, w.Layout]:
    path = tmp_path / "Every.wz"
    layout = w.write_archive(
        path, w.Dir("", [w.Dir("sub", [w.Img("every.img", EVERY_TYPE)])])
    )
    return path, layout


# --- the property tree -----------------------------------------------------


def test_every_property_type_parses_to_the_expected_tree(
    every_type: tuple[Path, w.Layout],
) -> None:
    path, layout = every_type
    archive = WzArchive.open(path)

    tree = archive.parse(archive.root.directories["sub"].images["every.img"])

    assert tree == _expected(layout, "sub/every.img")


def test_children_keep_the_archive_order(every_type: tuple[Path, w.Layout]) -> None:
    path, _ = every_type
    archive = WzArchive.open(path)

    tree = archive.parse(archive.root.directories["sub"].images["every.img"])

    assert list(tree.children) == [node.name for node in EVERY_TYPE]


def test_references_point_at_the_undecoded_bytes(
    every_type: tuple[Path, w.Layout],
) -> None:
    path, _ = every_type
    archive = WzArchive.open(path)
    data = path.read_bytes()

    tree = archive.parse(archive.root.directories["sub"].images["every.img"])

    canvas = tree["canvas"]
    sound = tree["sound"]
    raw = tree["raw"]
    assert isinstance(canvas, CanvasNode)
    assert isinstance(sound, SoundNode)
    assert isinstance(raw, RawDataNode)
    ref = canvas.canvas
    assert (ref.width, ref.height, ref.format) == (4, 5, 2)
    assert data[ref.offset : ref.offset + ref.length] == PIXELS
    audio = sound.sound
    assert data[audio.offset : audio.offset + audio.length] == AUDIO
    assert audio.header_offset + audio.header_length == audio.offset
    assert data[raw.data.offset : raw.data.offset + raw.data.length] == RAW


def test_paths_walk_down_and_get_returns_none_for_a_missing_step(
    every_type: tuple[Path, w.Layout],
) -> None:
    path, _ = every_type
    archive = WzArchive.open(path)
    tree = archive.parse(archive.root.directories["sub"].images["every.img"])

    assert tree["info/move/0"] == IntNode(name="0", value=1)
    assert tree.get("info/nowhere") is None
    with pytest.raises(KeyError):
        tree["info/origin/x"]


def test_walk_yields_every_node_with_its_path(
    every_type: tuple[Path, w.Layout],
) -> None:
    path, _ = every_type
    archive = WzArchive.open(path)
    tree = archive.parse(archive.root.directories["sub"].images["every.img"])

    paths = [node_path for node_path, _ in tree.walk()]

    assert "info/move/0" in paths
    assert "canvas/origin" in paths
    assert "convex/2" in paths
    assert len(paths) == len(set(paths))


def test_directory_names_written_by_offset_read_like_inline_ones(
    tmp_path: Path,
) -> None:
    entries = [
        w.Dir("a", [w.Img("same.img", [w.Int("v", 1)])]),
        w.Dir("b", [w.Img("same.img", [w.Int("v", 2)])]),
    ]
    shared = WzArchive.open(_write(tmp_path / "shared.wz", entries, shared=True))
    inline = WzArchive.open(_write(tmp_path / "inline.wz", entries, shared=False))

    assert shared.path.stat().st_size < inline.path.stat().st_size
    for archive in (shared, inline):
        assert [path for path, _ in archive.images()] == ["a/same.img", "b/same.img"]
        second = archive.root.directories["b"].images["same.img"]
        assert archive.parse(second)["v"] == IntNode(name="v", value=2)


def _write(
    path: Path, entries: Sequence[w.Dir | w.Img], *, shared: bool = True
) -> Path:
    w.write_archive(path, w.Dir("", entries), shared_names=shared)
    return path


# --- versions --------------------------------------------------------------


@pytest.mark.parametrize("version", [83, 95, 176, 779])
def test_the_version_is_detected_from_the_header(tmp_path: Path, version: int) -> None:
    path = _write_version(tmp_path, version)

    assert WzArchive.open(path).version == version


def test_detection_picks_the_version_among_others_sharing_its_header_byte(
    tmp_path: Path,
) -> None:
    rivals = [
        v for v in range(1, 1000) if encrypted_version(v) == encrypted_version(95)
    ]
    assert len(rivals) > 1
    path = _write_version(tmp_path, 95)

    assert WzArchive.open(path).version == 95


def test_a_given_version_that_does_not_match_the_header_raises(
    tmp_path: Path,
) -> None:
    path = _write_version(tmp_path, 95)

    with pytest.raises(CorruptArchive, match="version 779"):
        WzArchive.open(path, version=779)


def test_an_empty_archive_has_no_version(tmp_path: Path) -> None:
    path = _write(tmp_path / "empty.wz", [])

    assert WzArchive.open(path).version is None


def _write_version(tmp_path: Path, version: int) -> Path:
    path = tmp_path / f"v{version}.wz"
    entries: list[w.Dir | w.Img] = [
        w.Dir("d", [w.Img("x.img", [w.Int("a", 1)])]),
        w.Img("y.img", [w.String("s", "v")]),
    ]
    w.write_archive(path, w.Dir("", entries), version=version)
    return path


# --- errors ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        (w.Bad("broken"), "unknown property type 42"),
        (w.BadExtended("broken"), "unknown extended object type 'Shape2D#Bogus'"),
    ],
)
def test_a_corrupted_node_raises_naming_the_archive_image_and_node(
    tmp_path: Path, bad: w.Property, reason: str
) -> None:
    path = tmp_path / "Corrupt.wz"
    tree = [w.Int("fine", 1), w.Prop("outer", [w.Prop("inner", [bad])])]
    w.write_archive(path, w.Dir("", [w.Img("bad.img", tree)]))
    archive = WzArchive.open(path)

    with pytest.raises(CorruptArchive) as caught:
        archive.parse(archive.root.images["bad.img"])

    error = caught.value
    assert error.archive == str(path)
    assert error.image == "bad.img"
    assert error.node == "outer/inner/broken"
    assert reason in str(error)
    assert str(path) in str(error)


def test_a_truncated_image_raises_naming_the_node_it_stopped_in(
    every_type: tuple[Path, w.Layout],
) -> None:
    path, layout = every_type
    offset, size = layout.images["sub/every.img"]
    data = path.read_bytes()[offset : offset + size]
    cut = data[: layout.payloads["sub/every.img/canvas"][0] - offset + 5]

    with pytest.raises(CorruptArchive) as caught:
        parse_image(cut, archive=path, image="every.img", base=offset)

    assert caught.value.image == "every.img"
    assert caught.value.node == "canvas"


@pytest.mark.parametrize("keep", [3, 20, 70])
def test_a_truncated_archive_raises_naming_the_archive(
    every_type: tuple[Path, w.Layout], keep: int
) -> None:
    path, _ = every_type
    path.write_bytes(path.read_bytes()[:keep])

    with pytest.raises(CorruptArchive) as caught:
        WzArchive.open(path)

    assert caught.value.archive == str(path)


def test_an_archive_cut_after_its_directory_raises_rather_than_listing_less(
    tmp_path: Path,
) -> None:
    # The header's size is rewritten to match, so only the directory's offsets
    # betray the cut: the images they point at are gone.
    path = tmp_path / "Cut.wz"
    layout = w.write_archive(
        path, w.Dir("", [w.Img("a.img", [w.Int("v", 1)]), w.Img("b.img", [])])
    )
    cut = layout.images["b.img"][0]
    data = bytearray(path.read_bytes()[:cut])
    data[4:12] = (cut - w.DATA_START).to_bytes(8, "little")
    path.write_bytes(bytes(data))

    with pytest.raises(CorruptArchive) as caught:
        WzArchive.open(path)

    assert caught.value.archive == str(path)


def test_an_image_whose_tree_ends_early_raises(tmp_path: Path) -> None:
    data, _ = w.image_bytes([w.Int("v", 1)])

    with pytest.raises(CorruptArchive, match="ends at offset"):
        parse_image(data + b"\x00", archive="x.wz", image="x.img")


def test_a_file_that_is_not_an_archive_raises(tmp_path: Path) -> None:
    path = tmp_path / "Not.wz"
    path.write_bytes(b"MZ" + bytes(100))

    with pytest.raises(CorruptArchive, match="PKG1"):
        WzArchive.open(path)
