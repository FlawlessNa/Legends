"""
One `.wz` file: its header, its version, and its directory.

The layout, as Classic's client stores it:

- **Header.** `PKG1`, a `uint64` data size (the file's length less the data
  start), a `uint32` data start, then a copyright string up to the data start.
- **Version.** At the data start, a `uint16`: `0xFF` XORed with each byte of
  the version's hash. The hash runs `h = 32 * h + ord(c) + 1` over the
  version's decimal digits. Several versions share each stored value, so
  `WzArchive.open` tries every candidate and keeps the one whose directory
  decodes to offsets that land on images.
- **Directory.** A compressed count, then that many entries. Each is a type
  byte (2: the name is elsewhere, at an `int32` offset from the data start,
  behind its own type byte; 3: a directory; 4: an image), the name, a
  compressed size and checksum, and an encrypted `uint32` offset
  (`decode_offset`). A directory's entries are at its offset.

Images are read on demand: `WzArchive.read` returns one image's bytes,
`WzArchive.parse` its property tree, and `WzArchive.pixels` one canvas's
pixels.
"""

import mmap
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .canvas import Pixels, decode_canvas
from .errors import CorruptArchive
from .image import parse_image
from .nodes import CanvasRef, PropertyNode
from .reader import BadFormat, ByteReader

MAGIC = b"PKG1"

# Versions up to this are tried when the version is detected. Classic is 779.
MAX_VERSION = 10_000

_OFFSET_KEY = 0x581C3F6D
_IMAGE_TAGS = frozenset({0x73, 0x1B})


def version_hash(version: int) -> int:
    """The hash the offsets are encrypted with, from the version's digits."""
    value = 0
    for digit in str(version):
        value = (32 * value + ord(digit) + 1) & 0xFFFFFFFF
    return value


def encrypted_version(version: int) -> int:
    """The `uint16` the header stores for `version`."""
    value = version_hash(version)
    return (
        0xFF
        ^ (value >> 24)
        ^ ((value >> 16) & 0xFF)
        ^ ((value >> 8) & 0xFF)
        ^ (value & 0xFF)
    )


def decode_offset(position: int, stored: int, *, data_start: int, key: int) -> int:
    """
    A directory entry's offset in the file.

    :param position: Where the stored offset is in the file.
    :param stored: The `uint32` stored there.
    :param data_start: The header's data start.
    :param key: `version_hash(version)`.
    """
    value = ((position - data_start) ^ 0xFFFFFFFF) & 0xFFFFFFFF
    value = (value * key) & 0xFFFFFFFF
    value = (value - _OFFSET_KEY) & 0xFFFFFFFF
    shift = value & 0x1F
    value = ((value << shift) | (value >> (32 - shift))) & 0xFFFFFFFF
    return ((value ^ stored) + 2 * data_start) & 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class ImageEntry:
    """
    An image's place in its archive.

    :ivar name: Such as `000001000.img`.
    :ivar offset: The image's first byte, from the start of the file.
    :ivar size: The image's length in bytes.
    :ivar checksum: As stored. Nothing checks it.
    """

    name: str
    offset: int
    size: int
    checksum: int


@dataclass(frozen=True, slots=True)
class WzDirectory:
    """
    A directory inside one archive file, with everything below it.

    :ivar name: Empty for the archive's root.
    """

    name: str
    directories: Mapping[str, WzDirectory]
    images: Mapping[str, ImageEntry]


@dataclass(frozen=True, slots=True)
class WzArchive:
    """
    One `.wz` file, with its directory read.

    :ivar path: The file.
    :ivar version: The version its offsets are encrypted with, or `None` when
        its directory is empty, so nothing in it is encrypted.
    :ivar data_start: From the header.
    :ivar root: The archive's directory tree.
    """

    path: Path
    version: int | None
    data_start: int
    root: WzDirectory

    @classmethod
    def open(cls, path: Path, *, version: int | None = None) -> WzArchive:
        """
        Reads `path`'s header and directory.

        :param version: The version, when it's known. By default it's detected.
        :raises CorruptArchive: The file isn't a WZ archive, is truncated, or no
            version decodes its directory, or more than one does.
        :raises FileNotFoundError: There is no such file.
        """
        with path.open("rb") as file:
            if path.stat().st_size == 0:
                raise CorruptArchive(path, None, None, "the file is empty")
            with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
                reader = ByteReader(data)
                try:
                    return cls._read(path, reader, version)
                finally:
                    reader.release()

    @classmethod
    def _read(cls, path: Path, reader: ByteReader, version: int | None) -> WzArchive:
        try:
            data_start, stored = _header(reader)
        except BadFormat as error:
            raise CorruptArchive(path, None, None, str(error)) from error
        if version is not None:
            candidates = [version]
            if encrypted_version(version) != stored:
                raise CorruptArchive(
                    path,
                    None,
                    None,
                    f"the header's version byte {stored:#x} doesn't match "
                    f"version {version}",
                )
        else:
            candidates = [
                v for v in range(1, MAX_VERSION) if encrypted_version(v) == stored
            ]
        found: list[tuple[int, WzDirectory]] = []
        failure = _DirectoryFailure("", "no version matches the header")
        for candidate in candidates:
            parser = _DirectoryParser(reader, data_start, version_hash(candidate))
            try:
                found.append((candidate, parser.directory("", data_start + 2)))
            except BadFormat as error:
                failure = _DirectoryFailure(parser.where(), str(error))
        if not found:
            reason = failure.reason
            if version is None:
                reason = (
                    f"no version up to {MAX_VERSION} decodes the directory "
                    f"(the last tried failed with: {reason})"
                )
            raise CorruptArchive(path, None, failure.where, reason)
        chosen: int | None = found[0][0]
        root = found[0][1]
        if not root.directories and not root.images and len(found) > 1:
            chosen = None
        elif any(other != root for _, other in found[1:]):
            versions = ", ".join(str(v) for v, _ in found)
            raise CorruptArchive(
                path, None, None, f"versions {versions} all decode the directory"
            )
        return cls(path=path, version=chosen, data_start=data_start, root=root)

    def read(self, entry: ImageEntry) -> bytes:
        """
        One image's bytes.

        :raises CorruptArchive: The file ends before the image does.
        """
        return self._bytes_at(entry.offset, entry.size, entry.name, None, "the image")

    def parse(self, entry: ImageEntry) -> PropertyNode:
        """
        One image's property tree, parsed afresh on every call.

        :raises CorruptArchive: The image doesn't parse.
        """
        return parse_image(
            self.read(entry), archive=self.path, image=entry.name, base=entry.offset
        )

    def pixels(self, entry: ImageEntry, canvas: CanvasRef, node: str) -> Pixels:
        """
        One canvas's pixels, decoded: `(height, width, 4)`, RGBA (`canvas`).

        :param entry: The image the canvas is in.
        :param canvas: The canvas, from that image's tree. Its offset counts
            from the start of the file.
        :param node: The canvas's path inside the image, for errors.
        :raises UnsupportedFormat: The pixel format isn't supported.
        :raises CorruptArchive: The file ends before the pixels do, or they
            don't decode.
        """
        image = entry.name
        data = self._bytes_at(canvas.offset, canvas.length, image, node, "the canvas")
        return decode_canvas(data, canvas, archive=self.path, image=image, node=node)

    def _bytes_at(
        self, offset: int, size: int, image: str, node: str | None, what: str
    ) -> bytes:
        with self.path.open("rb") as file:
            file.seek(offset)
            data = file.read(size)
        if len(data) != size:
            raise CorruptArchive(
                self.path,
                image,
                node,
                f"{what} is {size} bytes at offset {offset}, "
                f"but the file ends after {len(data)}",
            )
        return data

    def images(self) -> list[tuple[str, ImageEntry]]:
        """Every image in the archive, with its path from the archive's root."""
        found: list[tuple[str, ImageEntry]] = []

        def collect(directory: WzDirectory, prefix: str) -> None:
            for name, entry in directory.images.items():
                found.append((f"{prefix}{name}", entry))
            for name, child in directory.directories.items():
                collect(child, f"{prefix}{name}/")

        collect(self.root, "")
        return found


@dataclass(frozen=True, slots=True)
class _DirectoryFailure:
    where: str
    reason: str


def _header(reader: ByteReader) -> tuple[int, int]:
    """The data start and the stored version, after checking the header."""
    magic = reader.raw(4)
    if magic != MAGIC:
        raise BadFormat(f"the file starts with {magic!r}, not {MAGIC!r}")
    size = reader.u64()
    data_start = reader.u32()
    if data_start < 16:
        raise BadFormat(f"the data start {data_start} is inside the header")
    if data_start + size != len(reader):
        raise BadFormat(
            f"the header says {data_start + size} bytes, but the file is {len(reader)}"
        )
    reader.seek(data_start)
    return data_start, reader.u16()


class _DirectoryParser:
    def __init__(self, reader: ByteReader, data_start: int, key: int) -> None:
        self._reader = reader
        self._data_start = data_start
        self._key = key
        self._path: list[str] = []

    def where(self) -> str:
        return "/".join(self._path)

    def directory(self, name: str, offset: int) -> WzDirectory:
        reader = self._reader
        reader.seek(offset)
        count = reader.compressed_int()
        if count < 0:
            raise BadFormat(f"a directory has {count} entries")
        pending: list[tuple[str, int]] = []
        images: dict[str, ImageEntry] = {}
        names: set[str] = set()
        for _ in range(count):
            kind = reader.u8()
            if kind == 2:
                name_offset = reader.i32()
                resume = reader.pos
                reader.seek(self._data_start + name_offset)
                kind = reader.u8()
                entry_name = reader.wz_string()
                reader.seek(resume)
            elif kind in (3, 4):
                entry_name = reader.wz_string()
            else:
                raise BadFormat(f"unknown directory entry type {kind}")
            if entry_name in names:
                raise BadFormat(f"{entry_name!r} appears twice in its directory")
            names.add(entry_name)
            size = reader.compressed_int()
            checksum = reader.compressed_int()
            position = reader.pos
            entry_offset = decode_offset(
                position, reader.u32(), data_start=self._data_start, key=self._key
            )
            if not self._data_start <= entry_offset < len(reader):
                raise BadFormat(
                    f"{entry_name!r} is at offset {entry_offset}, "
                    f"outside the file's {len(reader)} bytes"
                )
            if kind == 3:
                pending.append((entry_name, entry_offset))
            elif kind == 4:
                self._check_image(entry_name, entry_offset, size)
                images[entry_name] = ImageEntry(
                    name=entry_name, offset=entry_offset, size=size, checksum=checksum
                )
            else:
                raise BadFormat(f"{entry_name!r} has unknown entry type {kind}")
        directories: dict[str, WzDirectory] = {}
        for child, child_offset in pending:
            self._path.append(child)
            directories[child] = self.directory(child, child_offset)
            self._path.pop()
        return WzDirectory(name=name, directories=directories, images=images)

    def _check_image(self, name: str, offset: int, size: int) -> None:
        reader = self._reader
        if size <= 0 or offset + size > len(reader):
            raise BadFormat(
                f"{name!r} is {size} bytes at offset {offset}, "
                f"past the file's {len(reader)} bytes"
            )
        resume = reader.pos
        reader.seek(offset)
        tag = reader.u8()
        reader.seek(resume)
        if tag not in _IMAGE_TAGS:
            raise BadFormat(f"{name!r} starts with {tag:#04x}, not an image header")
