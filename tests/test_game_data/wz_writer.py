"""
Writes synthetic WZ archives, so tests never need the real client's files.

Test-only. It writes the format `game_data.archive` reads, independently of the
reader's code: a tree described with the classes below goes to bytes, and the
tests read it back. `write_pack` writes a `.ms` v2 pack of images.

- `Img` and `Dir` describe an archive's directory. `write_archive` writes one
  `.wz` file and `write_tree` writes a split tree: a stub, its parts and the
  `.ini` that counts them.
- The property classes (`Prop`, `Short`, `Canvas`, ...) describe an image's
  tree, one class per property type. `Bad` and `BadExtended` write a type the
  format doesn't have, to corrupt a fixture at a known node.
- A string the image has already written is written as an offset to the first
  copy, as the client does, so every tree exercises both kinds of string block.

`write_archive` returns a `Layout`: where each image and each canvas, sound and
raw-data payload landed in the file, so a test can build the references it
expects to read back.
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from game_data.archive.chacha20 import ChaCha20

DATA_START = 0x3C
COPYRIGHT = b"Package file v1.0 Copyright 2002 Wizet, ZMS\x00"
SOUND_HEADER = 51


# --- the property tree -----------------------------------------------------


@dataclass(frozen=True)
class Null:
    name: str


@dataclass(frozen=True)
class Short:
    name: str
    value: int


@dataclass(frozen=True)
class Int:
    name: str
    value: int
    code: int = 3  # 3 or 19: the client writes both


@dataclass(frozen=True)
class Long:
    name: str
    value: int


@dataclass(frozen=True)
class Float:
    name: str
    value: float


@dataclass(frozen=True)
class Double:
    name: str
    value: float


@dataclass(frozen=True)
class String:
    name: str
    value: str


@dataclass(frozen=True)
class Prop:
    name: str
    children: Sequence[Property] = ()


@dataclass(frozen=True)
class Vector:
    name: str
    x: int
    y: int


@dataclass(frozen=True)
class Uol:
    name: str
    path: str


@dataclass(frozen=True)
class Canvas:
    name: str
    width: int
    height: int
    pixels: bytes
    format: int = 1
    scale: int = 0
    children: Sequence[Property] = ()


@dataclass(frozen=True)
class Convex:
    name: str
    points: Sequence[tuple[int, int]]


@dataclass(frozen=True)
class Sound:
    name: str
    audio: bytes
    duration_ms: int
    wave_format: bytes = b"\x01\x00\x02\x00"


@dataclass(frozen=True)
class RawData:
    name: str
    payload: bytes
    children: Sequence[Property] = ()


@dataclass(frozen=True)
class Bad:
    """A property whose type byte the format doesn't have."""

    name: str
    code: int = 42


@dataclass(frozen=True)
class BadExtended:
    """An extended object whose type name the format doesn't have."""

    name: str
    type_name: str = "Shape2D#Bogus"


type Property = (
    Null
    | Short
    | Int
    | Long
    | Float
    | Double
    | String
    | Prop
    | Vector
    | Uol
    | Canvas
    | Convex
    | Sound
    | RawData
    | Bad
    | BadExtended
)


# --- the directory ---------------------------------------------------------


@dataclass(frozen=True)
class Img:
    name: str
    children: Sequence[Property] = ()


@dataclass(frozen=True)
class Dir:
    name: str
    entries: Sequence[Dir | Img] = ()


@dataclass
class Layout:
    """
    Where things landed in a written archive, by path.

    :ivar images: Image path from the archive root -> (offset, size).
    :ivar payloads: `image path/node path` -> (offset, length) of a canvas's
        pixels, a sound's audio or raw data's bytes. A sound's header offset is
        under the same key plus `#header`.
    """

    images: dict[str, tuple[int, int]] = field(default_factory=dict)
    payloads: dict[str, tuple[int, int]] = field(default_factory=dict)


# --- encodings -------------------------------------------------------------


def compressed_int(value: int) -> bytes:
    if -127 <= value <= 127:
        return struct.pack("<b", value)
    return b"\x80" + struct.pack("<i", value)


def compressed_long(value: int) -> bytes:
    if -127 <= value <= 127:
        return struct.pack("<b", value)
    return b"\x80" + struct.pack("<q", value)


def wz_string(value: str) -> bytes:
    """A masked string: bytes when it fits in Latin-1, UTF-16 otherwise."""
    if not value:
        return b"\x00"
    try:
        raw = value.encode("latin-1")
    except UnicodeEncodeError:
        units = struct.unpack(
            f"<{len(value.encode('utf-16-le')) // 2}H", value.encode("utf-16-le")
        )
        length = len(units)
        head = (
            struct.pack("<b", length)
            if length < 127
            else b"\x7f" + struct.pack("<i", length)
        )
        masked = [(unit ^ ((0xAAAA + i) & 0xFFFF)) for i, unit in enumerate(units)]
        return head + struct.pack(f"<{length}H", *masked)
    length = len(raw)
    head = (
        struct.pack("<b", -length)
        if length <= 127
        else b"\x80" + struct.pack("<i", length)
    )
    return head + bytes(b ^ ((0xAA + i) & 0xFF) for i, b in enumerate(raw))


def version_hash(version: int) -> int:
    value = 0
    for digit in str(version):
        value = (32 * value + ord(digit) + 1) & 0xFFFFFFFF
    return value


def encrypted_version(version: int) -> int:
    value = version_hash(version)
    result = 0xFF
    for shift in (24, 16, 8, 0):
        result ^= (value >> shift) & 0xFF
    return result


def encrypt_offset(position: int, offset: int, *, version: int) -> int:
    """The `uint32` to store at `position` so that it decodes to `offset`."""
    value = ((position - DATA_START) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    value = (value * version_hash(version)) & 0xFFFFFFFF
    value = (value - 0x581C3F6D) & 0xFFFFFFFF
    shift = value & 0x1F
    value = ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF
    return value ^ ((offset - 2 * DATA_START) & 0xFFFFFFFF)


# --- images ----------------------------------------------------------------


class _ImageWriter:
    """Writes one image. Payload positions are relative to the image's start."""

    def __init__(self) -> None:
        self.out = bytearray()
        self.strings: dict[str, int] = {}
        self.payloads: dict[str, tuple[int, int]] = {}

    def string_block(self, value: str, *, inline: int, offset: int) -> None:
        known = self.strings.get(value)
        if known is not None:
            self.out += bytes([offset]) + struct.pack("<i", known)
            return
        self.out.append(inline)
        self.strings[value] = len(self.out)
        self.out += wz_string(value)

    def name(self, value: str) -> None:
        self.string_block(value, inline=0x00, offset=0x01)

    def type_name(self, value: str) -> None:
        self.string_block(value, inline=0x73, offset=0x1B)

    def property_list(self, children: Sequence[Property], path: str) -> None:
        self.out += compressed_int(len(children))
        for child in children:
            child_path = f"{path}/{child.name}" if path else child.name
            self.name(child.name)
            self.property(child, child_path)

    def property(self, node: Property, path: str) -> None:
        out = self.out
        match node:
            case Null():
                out.append(0)
            case Short(value=value):
                out += b"\x02" + struct.pack("<h", value)
            case Int(value=value, code=code):
                out += bytes([code]) + compressed_int(value)
            case Long(value=value):
                out += b"\x14" + compressed_long(value)
            case Float(value=value):
                out += b"\x04" + (
                    b"\x00" if value == 0 else b"\x80" + struct.pack("<f", value)
                )
            case Double(value=value):
                out += b"\x05" + struct.pack("<d", value)
            case String(value=value):
                out.append(8)
                self.name(value)
            case Bad(code=code):
                out.append(code)
            case _:
                out.append(9)
                size_at = len(out)
                out += b"\x00\x00\x00\x00"
                self.extended(node, path)
                struct.pack_into("<I", out, size_at, len(out) - size_at - 4)

    def extended(self, node: Property, path: str) -> None:
        out = self.out
        match node:
            case Prop(children=children):
                self.type_name("Property")
                out += b"\x00\x00"
                self.property_list(children, path)
            case Vector(x=x, y=y):
                self.type_name("Shape2D#Vector2D")
                out += compressed_int(x) + compressed_int(y)
            case Uol(path=target):
                self.type_name("UOL")
                out.append(0)
                self.name(target)
            case Convex(points=points):
                self.type_name("Shape2D#Convex2D")
                out += compressed_int(len(points))
                for x, y in points:
                    self.type_name("Shape2D#Vector2D")
                    out += compressed_int(x) + compressed_int(y)
            case Canvas():
                self.type_name("Canvas")
                out.append(0)
                self.optional_properties(node.children, path)
                out += compressed_int(node.width) + compressed_int(node.height)
                out += compressed_int(node.format) + bytes([node.scale])
                out += struct.pack("<i", 0) + struct.pack("<i", len(node.pixels) + 1)
                out.append(0)
                self.payloads[path] = (len(out), len(node.pixels))
                out += node.pixels
            case Sound():
                self.type_name("Sound_DX8")
                out.append(0)
                out += compressed_int(len(node.audio))
                out += compressed_int(node.duration_ms)
                header = bytes(SOUND_HEADER) + bytes([len(node.wave_format)])
                self.payloads[f"{path}#header"] = (
                    len(out),
                    len(header) + len(node.wave_format),
                )
                out += header + node.wave_format
                self.payloads[path] = (len(out), len(node.audio))
                out += node.audio
            case RawData():
                self.type_name("RawData")
                out.append(1)
                self.optional_properties(node.children, path)
                out += compressed_int(len(node.payload))
                self.payloads[path] = (len(out), len(node.payload))
                out += node.payload
            case BadExtended(type_name=type_name):
                self.type_name(type_name)
            case _:
                raise TypeError(f"{node!r} is not an extended object")

    def optional_properties(self, children: Sequence[Property], path: str) -> None:
        if children:
            self.out += b"\x01\x00\x00"
            self.property_list(children, path)
        else:
            self.out.append(0)


def image_bytes(
    children: Sequence[Property],
) -> tuple[bytes, dict[str, tuple[int, int]]]:
    """
    One image's bytes, and its payloads' positions from the image's start.
    """
    writer = _ImageWriter()
    writer.type_name("Property")
    writer.out += b"\x00\x00"
    writer.property_list(children, "")
    return bytes(writer.out), writer.payloads


# --- archives --------------------------------------------------------------


def archive_bytes(
    root: Dir,
    *,
    version: int = 779,
    shared_names: bool = True,
) -> tuple[bytes, Layout]:
    """
    A whole `.wz` file.

    :param shared_names: An entry whose kind and name were already written
        elsewhere in the directory is written as an offset to them (entry type
        2), whose type byte then says what the entry is.
    """
    images: list[tuple[str, Img, bytes, dict[str, tuple[int, int]]]] = []
    directories: list[tuple[Dir, str]] = []

    def collect(directory: Dir, prefix: str) -> None:
        directories.append((directory, prefix))
        for entry in directory.entries:
            path = f"{prefix}{entry.name}"
            if isinstance(entry, Img):
                data, payloads = image_bytes(entry.children)
                images.append((path, entry, data, payloads))
            else:
                collect(entry, f"{path}/")

    collect(root, "")

    # Directory blocks don't depend on where anything is: offsets are 4 bytes.
    # So lay them out first, then the images after them.
    written_names: dict[tuple[int, str], int] = {}
    blocks: dict[str, bytearray] = {}
    fixups: dict[str, list[tuple[int, str]]] = {}
    cursor = DATA_START + 2
    starts: dict[str, int] = {}
    image_data = {path: data for path, _, data, _ in images}
    for directory, prefix in directories:
        starts[prefix] = cursor
        block = bytearray(compressed_int(len(directory.entries)))
        pending: list[tuple[int, str]] = []
        for entry in directory.entries:
            path = f"{prefix}{entry.name}"
            kind = 4 if isinstance(entry, Img) else 3
            known = written_names.get((kind, entry.name)) if shared_names else None
            if known is not None:
                block += b"\x02" + struct.pack("<i", known - DATA_START)
            else:
                written_names[kind, entry.name] = cursor + len(block)
                block += bytes([kind]) + wz_string(entry.name)
            size = len(image_data[path]) if kind == 4 else 0
            block += compressed_int(size) + compressed_int(
                sum(image_data.get(path, b"")) & 0x7F
            )
            pending.append((len(block), path if kind == 4 else f"{path}/"))
            block += b"\x00\x00\x00\x00"
        blocks[prefix] = block
        fixups[prefix] = pending
        cursor += len(block)

    layout = Layout()
    for path, _, data, payloads in images:
        layout.images[path] = (cursor, len(data))
        for node_path, (offset, length) in payloads.items():
            layout.payloads[f"{path}/{node_path}"] = (cursor + offset, length)
        cursor += len(data)

    out = bytearray(b"PKG1")
    out += struct.pack("<Q", cursor - DATA_START) + struct.pack("<I", DATA_START)
    out += COPYRIGHT.ljust(DATA_START - len(out), b"\x00")
    out += struct.pack("<H", encrypted_version(version))
    for _, prefix in directories:
        block = blocks[prefix]
        for at, target in fixups[prefix]:
            offset = (
                starts[target] if target.endswith("/") else layout.images[target][0]
            )
            position = starts[prefix] + at
            struct.pack_into(
                "<I", block, at, encrypt_offset(position, offset, version=version)
            )
        out += block
    for path, _, data, _ in images:
        out += data
    assert len(out) == cursor
    return bytes(out), layout


def write_archive(
    path: Path, root: Dir, *, version: int = 779, shared_names: bool = True
) -> Layout:
    data, layout = archive_bytes(root, version=version, shared_names=shared_names)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return layout


def write_tree(
    folder: Path,
    stub: Sequence[Dir | Img],
    parts: Sequence[Sequence[Dir | Img]] = (),
    *,
    version: int = 779,
    ini: bool = True,
) -> dict[Path, Layout]:
    """
    A tree as Classic splits it: `<folder name>.wz`, then one
    `<folder name>_NNN.wz` per part, and an `.ini` with the last part's number.

    :param ini: Write the `.ini`. Without it, only the stub is the tree.
    """
    name = folder.name
    layouts = {
        folder / f"{name}.wz": write_archive(
            folder / f"{name}.wz", Dir("", stub), version=version
        )
    }
    for index, entries in enumerate(parts):
        file = folder / f"{name}_{index:03d}.wz"
        layouts[file] = write_archive(file, Dir("", entries), version=version)
    if ini:
        (folder / f"{name}.ini").write_text(f"LastWzIndex|{len(parts) - 1}\n")
    return layouts


# --- .ms packs -------------------------------------------------------------
#
# The layout follows wzlib-rs's `build_ms_file_v2` (`src/wz/ms_file.rs`, MIT,
# Copyright (c) 2026 wzlib-rs contributors). The key derivation is written
# here again rather than imported from the reader, so the two can disagree.
# The cipher itself is the reader's `ChaCha20`, which the RFC 8439 vector pins.

PACK_VERSION = 4
PACK_SALT = "s4lt#Synthetic!"

_OBSCURE = bytes.fromhex(
    "7b2f3548439502b9 ae91a6e1d8d624b4 33101d3dc1bbc6f4 a5feb3696b56e475"
)


@dataclass(frozen=True)
class Blob:
    """A pack entry that isn't an image, such as `pack_ignore.txt`."""

    name: str
    data: bytes


def _fnv(text: str) -> int:
    value = 0x811C9DC5
    for unit in text.encode("utf-16-le")[::2]:
        value = ((value ^ unit) * 0x01000193) % 2**32
    return value


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _pack_key(text: str, *, entry: bool) -> bytes:
    """The header key, or with `entry` the entry table's, for name + salt."""
    raw = bytearray()
    for i in range(32):
        if entry:
            char = ord(text[len(text) - 1 - i % len(text)]) % 256
            raw.append((i + (i % 3 + 2) * char) % 256)
        else:
            raw.append((ord(text[i % len(text)]) + i) % 256)
    return _xor(bytes(raw), _OBSCURE)


def _image_key(salt: str, name: str, entry_key: bytes) -> bytes:
    digits = [ord(c) - ord("0") for c in str(_fnv(salt))]
    n = len(digits)
    raw = bytearray()
    for i in range(32):
        factor = (
            digits[i % n] % 2
            + entry_key[(digits[(i + 2) % n] + i) % 16]
            + (digits[(i + 1) % n] + i) % 5
        )
        raw.append((i + ord(name[i % len(name)]) * factor) % 256)
    return _xor(bytes(raw), _OBSCURE)


def _image_nonce(salt: str) -> tuple[bytes, int]:
    first = _fnv(salt)
    data = bytearray(struct.pack("<III", first, first >> 1, (first >> 1) ^ 0x6C))
    for i in range(12):
        mix = -i + 11 * (i // 11) + ((90 + 43 * i) ^ (i >> 2)) + ((8 * i) ^ (17 * i))
        data[i] ^= mix % 256
    return b"\x00" * 4 + bytes(data[:8]), struct.unpack("<I", data[8:])[0]


class _TableWriter:
    """Mirrors the reader's stream: rewinds the counter when a write fills a block."""

    def __init__(self, key: bytes) -> None:
        self.cipher = ChaCha20(key, bytes(12))
        self.out = bytearray()
        self.pending = bytearray()

    def write(self, data: bytes) -> None:
        for byte in data:
            self.pending.append(byte)
            if len(self.pending) == 64:
                self.out += self.cipher.process(bytes(self.pending))
                self.pending.clear()
        if data and not self.pending:
            self.cipher.reset_counter()

    def i32(self, value: int) -> None:
        self.write(struct.pack("<i", value))

    def finish(self) -> bytes:
        if self.pending:
            self.out += self.cipher.process(bytes(self.pending).ljust(64, b"\x00"))
        return bytes(self.out)


def _align(size: int) -> int:
    return -(-size // 1024) * 1024


def pack_bytes(
    file_name: str,
    entries: Sequence[Img | Blob],
    *,
    salt: str = PACK_SALT,
    version: int = PACK_VERSION,
) -> bytes:
    """
    A whole `.ms` v2 pack. Each `Img`'s name is its full path, such as
    `Mob/0000001.img`.

    :param version: The version the header stores. Anything but 4 writes only
        the prefix, the version byte and padding, which is as far as a reader
        gets before refusing it.
    """
    lower = file_name.lower().encode()
    prefix = bytes(
        (i * 0x41C64E6D + 0x3039) // 65536 % 256 for i in range(sum(lower) % 312 + 30)
    )
    shifted = bytes((b - 256 if b > 127 else b) // 2 % 256 for b in prefix)
    out = bytearray(prefix)
    out.append(version ^ shifted[0])
    if version != PACK_VERSION:
        return bytes(out + bytes(256))

    stored_length = len(salt) ^ shifted[0]
    out += struct.pack("<i", stored_length)
    unit_sum = 0
    for i, char in enumerate(salt):
        a = next(a for a in range(256) if ((a | 0x4B) * 2 - a - 75) % 256 == ord(char))
        low = a ^ shifted[i]
        high = 0xFF if low > 127 else 0
        out += bytes([low, high])
        unit_sum += low + 256 * high

    key = file_name.lower() + salt
    total = stored_length + out[len(prefix)] + PACK_VERSION + len(entries) + unit_sum
    header = struct.pack("<iI", total, len(entries)).ljust(64, b"\x00")
    out += ChaCha20(_pack_key(key, entry=False), bytes(12)).process(header)
    out += bytes(8 + sum(3 * b for b in lower) % 212)

    contents = [
        (
            entry.name,
            image_bytes(entry.children)[0] if isinstance(entry, Img) else entry.data,
        )
        for entry in entries
    ]
    table = _TableWriter(_pack_key(key, entry=True))
    block = 0
    keys: list[bytes] = []
    for index, (name, data) in enumerate(contents):
        entry_key = bytes((index * 31 + i * 7 + 1) % 256 for i in range(16))
        keys.append(entry_key)
        aligned = _align(len(data))
        table.i32(len(name))
        table.write(name.encode("utf-16-le"))
        for value in (
            block + len(data) + aligned + sum(entry_key),  # checksum
            0,  # flags
            block,
            len(data),
            aligned,
            0,
            0,
        ):
            table.i32(value)
        table.write(entry_key)
        table.i32(0)
        table.i32(0)
        block += aligned // 1024
    out += table.finish()
    out += bytes(_align(len(out)) - len(out))

    nonce, counter = _image_nonce(salt)
    for (name, data), entry_key in zip(contents, keys, strict=True):
        head = ChaCha20(_image_key(salt, name, entry_key), nonce, counter).process(
            data[:1024]
        )
        out += (head + data[1024:]).ljust(_align(len(data)), b"\x00")
    return bytes(out)


def write_pack(
    path: Path,
    entries: Sequence[Img | Blob],
    *,
    salt: str = PACK_SALT,
    version: int = PACK_VERSION,
) -> None:
    """A pack at `path`, keyed by its file name, as the client's are."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pack_bytes(path.name, entries, salt=salt, version=version))
