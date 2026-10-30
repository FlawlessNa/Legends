# Ported from wzlib-rs, `src/wz/ms_file.rs` (https://github.com/apredovic419/
# wzlib-rs, commit 0463e2e): `parse_ms_file_v2`, `derive_key_core`,
# `derive_chacha_key`, `derive_img_key_core`, `derive_img_key_v2`,
# `derive_img_nonce_counter`, `ChaCha20StreamReader`, `decrypt_entry_v2` and
# `CHACHA20_KEY_OBSCURE`. MIT License, Copyright (c) 2026 wzlib-rs
# contributors: the permission notice is in that repository's LICENSE file, and
# applies to this file's ported parts.
"""
One `.ms` pack, as found in `Data\\Packs`: its entry table, and its entries.

A pack holds images under their full path, such as `Mob/0000001.img`, each
encrypted with ChaCha20. Decrypted, an entry is an ordinary image, which
`parse_image` reads. Only v2 is implemented; v1 (Snow2) raises
`UnsupportedFormat`. The layout:

- **Prefix.** `rbc = sum(lowercase file name bytes) % 312 + 30` random bytes.
  Each is shifted right by one, arithmetically, to give the `shifted` bytes
  the rest is masked with.
- **Version.** One byte, `shifted[0]` XORed with the version: 4 for v2.
- **Salt.** An `int32` whose low byte, XORed with `shifted[0]`, is the salt's
  length, then that many UTF-16 units. Unit `i`'s low byte, XORed with
  `shifted[i]`, is `a`, and the salt's character is `((a | 0x4B) << 1) - a - 75`.
- **Header.** One ChaCha20 block, keyed by the lowercase file name plus the
  salt (`_file_key`): an `int32` hash and an `int32` entry count.
- **Entry table.** After `sum(3 * name bytes) % 212 + 72` bytes from the header,
  a ChaCha20 stream with the entry key (`_EntryTable`). Each entry is a
  length-prefixed UTF-16 name, seven `int32`s (checksum, flags, start block,
  size, aligned size, two unknown), a 16-byte key, and two unknown `int32`s.
- **Data.** From the end of the table, aligned up to 1024 bytes, each entry at
  its start block times 1024. **Only the first `min(size, 1024)` bytes of an
  entry are encrypted**, with a key from the salt, the entry's name and its
  key (`_image_key`); the rest is plain.

The header hash and each entry's checksum are checked, so a wrong key fails
loudly rather than decoding garbage.
"""

import mmap
import struct
from collections.abc import Buffer
from dataclasses import dataclass, field
from pathlib import Path

from .canvas import Pixels, decode_canvas
from .chacha20 import BLOCK_SIZE, NONCE_SIZE, ChaCha20
from .errors import CorruptArchive, UnsupportedFormat
from .image import parse_image
from .nodes import CanvasRef, PropertyNode
from .reader import BadFormat, ByteReader, OutOfBounds

VERSION = 4

# The bytes of each entry that are encrypted; the rest of it is plain.
ENCRYPTED_SIZE = 1024
# Entries start on, and the data starts at, a multiple of this.
ALIGNMENT = 1024

_KEY_SIZE = 32
_ENTRY_KEY_SIZE = 16
_NO_NONCE = bytes(NONCE_SIZE)
# The smallest entry in the table: a one-unit name, seven `int32`s, a 16-byte
# key and two `int32`s.
_MIN_ENTRY = 4 + 2 + 7 * 4 + _ENTRY_KEY_SIZE + 2 * 4
_FNV_OFFSET = 0x811C9DC5
_FNV_PRIME = 0x01000193
_MASK = 0xFFFFFFFF

# XORed into every ChaCha20 key the pack derives.
CHACHA20_KEY_OBSCURE = bytes(
    (
        0x7B, 0x2F, 0x35, 0x48, 0x43, 0x95, 0x02, 0xB9,
        0xAE, 0x91, 0xA6, 0xE1, 0xD8, 0xD6, 0x24, 0xB4,
        0x33, 0x10, 0x1D, 0x3D, 0xC1, 0xBB, 0xC6, 0xF4,
        0xA5, 0xFE, 0xB3, 0x69, 0x6B, 0x56, 0xE4, 0x75,
    )
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class PackEntry:
    """
    An entry's place in its pack.

    :ivar name: Its full path, such as `Mob/0000001.img`.
    :ivar offset: Its first byte, from the start of the file.
    :ivar size: Its length in bytes.
    :ivar key: The 16 bytes its image key is derived from.
    """

    name: str
    offset: int
    size: int
    key: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class MsPack:
    """
    One `.ms` pack, with its entry table read.

    :ivar path: The file.
    :ivar entries: In the order the table lists them.
    """

    path: Path
    entries: tuple[PackEntry, ...]
    _salt: str = field(repr=False)

    @classmethod
    def open(cls, path: Path) -> MsPack:
        """
        Reads `path`'s header and entry table.

        :raises UnsupportedFormat: The version byte doesn't decode to v2.
        :raises CorruptArchive: The file is truncated, or its header or table
            don't decode.
        :raises FileNotFoundError: There is no such file.
        """
        with path.open("rb") as file:
            if path.stat().st_size == 0:
                raise CorruptArchive(path, None, None, "the file is empty")
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
                table = _TableParser(path, data)
                try:
                    salt, entries = table.parse()
                except BadFormat as error:
                    raise CorruptArchive(path, None, table.where, str(error)) from error
                finally:
                    table.release()
        return cls(path=path, entries=tuple(entries), _salt=salt)

    def read(self, entry: PackEntry) -> bytes:
        """
        One entry's decrypted bytes.

        :raises CorruptArchive: The file ends before the entry does.
        """
        with self.path.open("rb") as file:
            file.seek(entry.offset)
            data = file.read(entry.size)
        if len(data) != entry.size:
            raise CorruptArchive(
                self.path,
                entry.name,
                None,
                f"the entry is {entry.size} bytes at offset {entry.offset}, "
                f"but the file ends after {len(data)}",
            )
        nonce, counter = _image_nonce(self._salt)
        cipher = ChaCha20(_image_key(self._salt, entry.name, entry.key), nonce, counter)
        return cipher.process(data[:ENCRYPTED_SIZE]) + data[ENCRYPTED_SIZE:]

    def parse(self, entry: PackEntry) -> PropertyNode:
        """
        One entry's property tree, parsed afresh on every call. Its canvas,
        sound and raw-data offsets count from the entry's first decrypted byte,
        not from the start of the pack.

        :raises CorruptArchive: The entry doesn't parse.
        """
        return parse_image(self.read(entry), archive=self.path, image=entry.name)

    def pixels(self, entry: PackEntry, canvas: CanvasRef, node: str) -> Pixels:
        """
        One canvas's pixels, decoded: `(height, width, 4)`, RGBA (`canvas`).

        :param entry: The image the canvas is in.
        :param canvas: The canvas, from that image's tree. Its offset counts
            from the entry's first decrypted byte.
        :param node: The canvas's path inside the image, for errors.
        :raises UnsupportedFormat: The pixel format isn't supported.
        :raises CorruptArchive: The entry ends before the pixels do, or they
            don't decode.
        """
        end = canvas.offset + canvas.length
        if end > entry.size:
            raise CorruptArchive(
                self.path,
                entry.name,
                node,
                f"the canvas is {canvas.length} bytes at offset {canvas.offset}, "
                f"but the entry is {entry.size}",
            )
        if canvas.offset < ENCRYPTED_SIZE:
            data = self.read(entry)[canvas.offset : end]
        else:
            # Past the encrypted start, the entry is plain: read only the pixels.
            with self.path.open("rb") as file:
                file.seek(entry.offset + canvas.offset)
                data = file.read(canvas.length)
            if len(data) != canvas.length:
                raise CorruptArchive(
                    self.path,
                    entry.name,
                    node,
                    f"the file ends {canvas.length - len(data)} bytes into the canvas",
                )
        return decode_canvas(
            data, canvas, archive=self.path, image=entry.name, node=node
        )


class _TableParser:
    """Reads a pack's header and entry table, keeping where it got to."""

    def __init__(self, path: Path, data: Buffer) -> None:
        self._path = path
        self._reader = ByteReader(data)
        self.where = "the header"

    def release(self) -> None:
        self._reader.release()

    def parse(self) -> tuple[str, list[PackEntry]]:
        reader = self._reader
        name = self._path.name.lower()
        name_bytes = name.encode("utf-8")
        prefix = reader.raw(sum(name_bytes) % 312 + 30)
        shifted = bytes(((b ^ 0x80) - 0x80 >> 1) & 0xFF for b in prefix)
        stored_version = reader.u8()
        version = stored_version ^ shifted[0]
        if version != VERSION:
            raise UnsupportedFormat(
                self._path,
                None,
                None,
                f"the version byte decodes to {version}, but only v2 ({VERSION}, "
                "ChaCha20) is implemented",
            )

        self.where = "the salt"
        stored_length = reader.i32()
        length = (stored_length & 0xFF) ^ shifted[0]
        if length == 0 or length > len(shifted):
            raise BadFormat(f"the salt is {length} characters long")
        units = reader.raw(2 * length)
        salt = "".join(
            chr((((a | 0x4B) << 1) - a - 75) & 0xFF)
            for a in (shifted[i] ^ units[2 * i] for i in range(length))
        )
        unit_sum = sum(struct.unpack(f"<{length}H", units))

        self.where = "the header"
        key = name + salt
        header_at = reader.pos
        header = ChaCha20(_file_key(key, entry=False), _NO_NONCE).process(
            reader.raw(BLOCK_SIZE)
        )
        stored_hash, count = struct.unpack_from("<iI", header)
        expected = (stored_length + stored_version + VERSION + count + unit_sum) & _MASK
        if stored_hash & _MASK != expected:
            raise BadFormat(
                f"the header's hash is {stored_hash & _MASK:#x}, not {expected:#x}: "
                "it doesn't decrypt with the key from the file's name and salt"
            )
        table_at = header_at + 8 + sum(3 * b for b in name_bytes) % 212 + 64
        if count * _MIN_ENTRY > len(reader) - table_at:
            raise BadFormat(f"the header lists {count} entries, more than fit")

        table = _EntryTable(reader, table_at, _file_key(key, entry=True))
        listed: list[tuple[str, int, int, bytes]] = []
        for index in range(count):
            self.where = f"entry {index}"
            listed.append(self._entry(table))
        self.where = "the data"
        data_start = -(-table.end // ALIGNMENT) * ALIGNMENT
        entries: list[PackEntry] = []
        for entry_name, block, size, entry_key in listed:
            offset = data_start + block * ALIGNMENT
            if offset + size > len(reader):
                raise OutOfBounds(
                    f"{entry_name!r} is {size} bytes at offset {offset}, "
                    f"past the file's {len(reader)} bytes"
                )
            entries.append(PackEntry(entry_name, offset, size, entry_key))
        return salt, entries

    def _entry(self, table: _EntryTable) -> tuple[str, int, int, bytes]:
        length = table.i32()
        if length <= 0 or 2 * length > table.remaining:
            raise BadFormat(f"an entry's name is {length} characters long")
        name = table.raw(2 * length).decode("utf-16-le", "surrogatepass")
        self.where = name
        # One read per field, as the client reads them: where reads end decides
        # when the stream's counter rewinds.
        checksum, flags, block, size, aligned, unknown, _ = (
            table.i32() for _ in range(7)
        )
        entry_key = table.raw(_ENTRY_KEY_SIZE)
        table.i32()
        table.i32()
        if block < 0 or size < 0 or aligned < size:
            raise BadFormat(
                f"the entry is {size} bytes ({aligned} aligned) at block {block}"
            )
        expected = flags + block + size + aligned + unknown + sum(entry_key)
        if checksum != expected:
            raise BadFormat(f"the entry's checksum is {checksum}, not {expected}")
        return name, block, size, entry_key


class _EntryTable:
    """
    The entry table's ChaCha20 stream (`ChaCha20StreamReader`).

    It decrypts whole 64-byte blocks, and **rewinds its counter whenever a
    read ends exactly on the end of a block**: the next block is then
    decrypted with the first block's keystream again.
    """

    def __init__(self, reader: ByteReader, start: int, key: bytes) -> None:
        self._reader = reader
        self._cipher = ChaCha20(key, _NO_NONCE)
        self._buffer = b""
        self._used = 0
        reader.seek(start)

    @property
    def end(self) -> int:
        """Where the blocks read so far end in the file."""
        return self._reader.pos

    @property
    def remaining(self) -> int:
        """The bytes left to read, decrypted or not."""
        return len(self._buffer) - self._used + len(self._reader) - self._reader.pos

    def raw(self, size: int) -> bytes:
        out = bytearray()
        while len(out) < size:
            if self._used == len(self._buffer):
                self._buffer = self._cipher.process(self._reader.raw(BLOCK_SIZE))
                self._used = 0
            take = min(size - len(out), len(self._buffer) - self._used)
            out += self._buffer[self._used : self._used + take]
            self._used += take
        if self._used == len(self._buffer):
            self._cipher.reset_counter()
        return bytes(out)

    def i32(self) -> int:
        return struct.unpack("<i", self.raw(4))[0]


def _fnv1a(text: str) -> int:
    """FNV-1a over the UTF-16 code units of `text`."""
    value = _FNV_OFFSET
    for (unit,) in struct.iter_unpack("<H", text.encode("utf-16-le")):
        value = ((value ^ unit) * _FNV_PRIME) & _MASK
    return value


def _obscure(key: bytes) -> bytes:
    return bytes(k ^ o for k, o in zip(key, CHACHA20_KEY_OBSCURE, strict=True))


def _units(text: str) -> list[int]:
    return [unit for (unit,) in struct.iter_unpack("<H", text.encode("utf-16-le"))]


def _file_key(name_and_salt: str, *, entry: bool) -> bytes:
    """
    The header's key (`entry=False`) or the entry table's (`derive_chacha_key`).

    Header: `key[i] = char[i % n] + i`. Entry table:
    `key[i] = i + (i % 3 + 2) * char[n - 1 - i % n]`. Bytes wrap.
    """
    units = _units(name_and_salt)
    n = len(units)
    if entry:
        key = bytes(
            (i + (i % 3 + 2) * (units[n - 1 - i % n] & 0xFF)) & 0xFF
            for i in range(_KEY_SIZE)
        )
    else:
        key = bytes((units[i % n] + i) & 0xFF for i in range(_KEY_SIZE))
    return _obscure(key)


def _image_key(salt: str, name: str, entry_key: bytes) -> bytes:
    """An entry's key, from the salt, its name and its 16 bytes (`derive_img_key_v2`)."""
    digits = [int(d) for d in str(_fnv1a(salt))]
    count = len(digits)
    units = _units(name)
    key = bytes(
        (
            i
            + units[i % len(units)]
            * (
                digits[i % count] % 2
                + entry_key[(digits[(i + 2) % count] + i) % _ENTRY_KEY_SIZE]
                + (digits[(i + 1) % count] + i) % 5
            )
        )
        & 0xFF
        for i in range(_KEY_SIZE)
    )
    return _obscure(key)


def _image_nonce(salt: str) -> tuple[bytes, int]:
    """Every entry's nonce and starting block, from the salt (`derive_img_nonce_counter`)."""
    first = _fnv1a(salt)
    second = first >> 1
    mixed = bytearray(struct.pack("<3I", first, second, second ^ 0x6C))
    a, b, c, d = 0, 0, 90, 0
    for i in range(12):
        mixed[i] ^= (d + 11 * (i // 11) + (c ^ (i >> 2)) + (a ^ b)) & 0xFF
        d -= 1
        a += 8
        b += 17
        c += 43
    return bytes(4) + bytes(mixed[:8]), struct.unpack_from("<I", mixed, 8)[0]
