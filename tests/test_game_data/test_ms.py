"""
`.ms` packs and their cipher, against synthetic packs from `wz_writer`.

No client data is read here: every pack is written by the test that reads it.
"""

from pathlib import Path

import pytest

from game_data.archive import (
    ArchiveError,
    CanvasNode,
    CanvasRef,
    ChaCha20,
    CorruptArchive,
    IntNode,
    MsPack,
    UnsupportedFormat,
    WzArchive,
    parse_image,
)
from tests.test_game_data import wz_writer as w

# --- ChaCha20 ----------------------------------------------------------------

# RFC 8439 §2.4.2.
RFC_KEY = bytes(range(32))
RFC_NONCE = bytes.fromhex("000000000000004a00000000")
RFC_PLAINTEXT = (
    b"Ladies and Gentlemen of the class of '99: If I could offer you only one "
    b"tip for the future, sunscreen would be it."
)
RFC_CIPHERTEXT = bytes.fromhex(
    "6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b"  # pragma: allowlist secret
    "f91b65c5524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d8"  # pragma: allowlist secret
    "07ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"  # pragma: allowlist secret
    "5af90bbf74a35be6b40b8eedf2785e42874d"  # pragma: allowlist secret
)


def test_chacha20_reproduces_the_rfc_8439_vector() -> None:
    assert ChaCha20(RFC_KEY, RFC_NONCE, 1).process(RFC_PLAINTEXT) == RFC_CIPHERTEXT


def test_chacha20_decrypts_what_it_encrypts() -> None:
    assert ChaCha20(RFC_KEY, RFC_NONCE, 1).process(RFC_CIPHERTEXT) == RFC_PLAINTEXT


def test_chacha20_continues_the_stream_across_calls() -> None:
    cipher = ChaCha20(RFC_KEY, RFC_NONCE, 1)

    pieces = cipher.process(RFC_PLAINTEXT[:64]) + cipher.process(RFC_PLAINTEXT[64:])

    assert pieces == RFC_CIPHERTEXT


def test_reset_counter_rewinds_to_the_first_block() -> None:
    cipher = ChaCha20(RFC_KEY, RFC_NONCE, 7)
    first = cipher.keystream(64)
    assert cipher.counter == 8

    cipher.reset_counter()

    assert cipher.counter == 7
    assert cipher.keystream(64) == first


def test_the_counter_carries_into_the_nonce_when_it_wraps() -> None:
    wrapping = ChaCha20(RFC_KEY, bytes(12), 0xFFFFFFFF)
    wrapping.keystream(64)

    carried = ChaCha20(RFC_KEY, (1).to_bytes(4, "little") + bytes(8), 0)

    assert wrapping.keystream(64) == carried.keystream(64)


@pytest.mark.parametrize(("key", "nonce"), [(bytes(31), bytes(12)), (bytes(32), b"")])
def test_chacha20_rejects_a_wrong_sized_key_or_nonce(key: bytes, nonce: bytes) -> None:
    with pytest.raises(ValueError, match="ChaCha20"):
        ChaCha20(key, nonce)


# --- packs -------------------------------------------------------------------

PIXELS = bytes(range(256)) * 8

# The first entry's name is 16 characters, so its seventh `int32` ends exactly
# on the end of the table's first 64-byte block, and the stream rewinds its
# counter there. Every entry after it decrypts only if the reader does too.
# Longer than 1024 bytes, so only its start is encrypted.
LARGE = w.Img(
    "Mob/0000002.img",
    [
        w.Prop("info", [w.Int("level", 2), w.String("name", "x" * 40)]),
        w.Canvas("icon", width=32, height=32, pixels=PIXELS),
    ],
)
ENTRIES: list[w.Img | w.Blob] = [
    w.Img("Mob/00000001.img", [w.Prop("info", [w.Int("level", 1)])]),
    LARGE,
    w.Blob("Mob/pack_ignore.txt", b"ignore me\r\n"),
    *(w.Img(f"Mob/{n:07d}.img", [w.Int("n", n)]) for n in range(3, 40)),
]


@pytest.fixture
def pack(tmp_path: Path) -> MsPack:
    path = tmp_path / "Mob_00000.ms"
    w.write_pack(path, ENTRIES)
    return MsPack.open(path)


def test_a_pack_lists_every_entry_in_order(pack: MsPack) -> None:
    assert [entry.name for entry in pack.entries] == [e.name for e in ENTRIES]


def test_every_entry_decrypts_to_the_bytes_written(pack: MsPack) -> None:
    for written, entry in zip(ENTRIES, pack.entries, strict=True):
        expected = (
            w.image_bytes(written.children)[0]
            if isinstance(written, w.Img)
            else written.data
        )
        assert pack.read(entry) == expected, entry.name


def test_only_an_entrys_first_1024_bytes_are_encrypted(
    pack: MsPack, tmp_path: Path
) -> None:
    entry = pack.entries[1]
    plain = w.image_bytes(LARGE.children)[0]
    assert entry.size > 1024

    stored = (tmp_path / "Mob_00000.ms").read_bytes()[
        entry.offset : entry.offset + entry.size
    ]

    assert stored[1024:] == plain[1024:]
    assert stored[:1024] != plain[:1024]


def test_entries_parse_with_the_image_parser(pack: MsPack) -> None:
    for written, entry in zip(ENTRIES, pack.entries, strict=True):
        if isinstance(written, w.Img):
            expected = parse_image(
                w.image_bytes(written.children)[0], archive="", image=""
            )
            assert pack.parse(entry) == expected


def test_canvas_offsets_count_from_the_entrys_first_decrypted_byte(
    pack: MsPack,
) -> None:
    _, payloads = w.image_bytes(LARGE.children)

    icon = pack.parse(pack.entries[1])["icon"]

    assert isinstance(icon, CanvasNode)
    assert icon.canvas == CanvasRef(
        offset=payloads["icon"][0],
        length=len(PIXELS),
        format=1,
        scale=0,
        width=32,
        height=32,
    )


def test_an_empty_pack_has_no_entries(tmp_path: Path) -> None:
    path = tmp_path / "Skill_00000.ms"
    w.write_pack(path, [])

    assert MsPack.open(path).entries == ()


def test_the_keys_come_from_the_lowercase_file_name(tmp_path: Path) -> None:
    written = tmp_path / "written" / "Mob_00000.ms"
    w.write_pack(written, ENTRIES)
    upper = tmp_path / "upper" / "MOB_00000.MS"
    renamed = tmp_path / "renamed" / "Skill_00000.ms"
    for copy in (upper, renamed):
        copy.parent.mkdir()
        copy.write_bytes(written.read_bytes())

    assert [e.name for e in MsPack.open(upper).entries] == [e.name for e in ENTRIES]
    with pytest.raises(ArchiveError) as caught:
        MsPack.open(renamed)
    assert caught.value.archive == str(renamed)


@pytest.mark.parametrize("version", [2, 0, 7, 255])
def test_a_pack_that_is_not_v2_raises_unsupported_format(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "Mob_00000.ms"
    w.write_pack(path, ENTRIES, version=version)

    with pytest.raises(UnsupportedFormat, match=f"decodes to {version},") as caught:
        MsPack.open(path)

    assert caught.value.archive == str(path)


def test_a_corrupted_header_raises_naming_the_pack(tmp_path: Path) -> None:
    path = tmp_path / "Mob_00000.ms"
    w.write_pack(path, ENTRIES)
    data = bytearray(path.read_bytes())
    header = sum(path.name.lower().encode()) % 312 + 30 + 1 + 4 + 2 * len(w.PACK_SALT)
    data[header] ^= 0xFF
    path.write_bytes(bytes(data))

    with pytest.raises(CorruptArchive, match="hash") as caught:
        MsPack.open(path)

    assert caught.value.archive == str(path)


def test_a_truncated_pack_raises_naming_the_pack(tmp_path: Path) -> None:
    path = tmp_path / "Mob_00000.ms"
    w.write_pack(path, ENTRIES)
    path.write_bytes(path.read_bytes()[:2000])

    with pytest.raises(CorruptArchive) as caught:
        MsPack.open(path)

    assert caught.value.archive == str(path)


def test_an_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "Mob_00000.ms"
    path.write_bytes(b"")

    with pytest.raises(CorruptArchive, match="empty"):
        MsPack.open(path)


def test_a_corrupt_entry_raises_naming_the_pack_entry_and_node(tmp_path: Path) -> None:
    path = tmp_path / "Mob_00000.ms"
    w.write_pack(path, [w.Img("Mob/bad.img", [w.Prop("p", [w.Bad("x")])])])
    pack = MsPack.open(path)

    with pytest.raises(CorruptArchive) as caught:
        pack.parse(pack.entries[0])

    assert caught.value.archive == str(path)
    assert caught.value.image == "Mob/bad.img"
    assert caught.value.node == "p/x"


def test_an_entry_parses_the_same_way_as_in_an_archive(tmp_path: Path) -> None:
    children: list[w.Property] = [w.Prop("info", [w.Int("level", 3)])]
    w.write_pack(tmp_path / "Mob_00000.ms", [w.Img("Mob/0000003.img", children)])
    w.write_archive(tmp_path / "Mob.wz", w.Dir("", [w.Img("0000003.img", children)]))

    archive = WzArchive.open(tmp_path / "Mob.wz")
    pack = MsPack.open(tmp_path / "Mob_00000.ms")

    in_pack = pack.parse(pack.entries[0])
    assert in_pack == archive.parse(archive.root.images["0000003.img"])
    assert in_pack["info/level"] == IntNode(name="level", value=3)
