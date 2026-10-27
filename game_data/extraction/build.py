"""
Which Build of the client is installed: its archive files, and its build id.

A Build is identified by its files, never by a version number the client
reports. Its **archives** are every `.wz` under `Data` and every `.ms` in
`Data/Packs`, by their path from `Data`, `/`-separated.

The **build id** is the first 16 hex digits of a SHA-256 over every archive's
`(path, size, sha256)`, sorted by path. The same bytes give the same id
wherever they are installed and whenever they were copied, since neither the
folder nor the modification times go into it.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PACKS = "Packs"
BUILD_ID_LENGTH = 16


@dataclass(frozen=True, slots=True)
class ArchiveFile:
    """
    One archive or pack on disk, as `stat` sees it.

    :ivar path: From `Data`, `/`-separated, such as `Map/Map/Map0/Map0_000.wz`.
    :ivar size: In bytes.
    :ivar mtime_ns: Its modification time, in nanoseconds.
    """

    path: str
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class HashedArchive:
    """An archive with its contents' SHA-256, in hex."""

    path: str
    size: int
    mtime_ns: int
    sha256: str


def archive_files(data: Path) -> list[ArchiveFile]:
    """
    Every archive and pack under the client's `Data` folder, sorted by path.
    Only `stat`s them: nothing is read.
    """
    files = [*data.rglob("*.wz"), *(data / PACKS).glob("*.ms")]
    found: list[ArchiveFile] = []
    for file in files:
        if not file.is_file():
            continue
        stat = file.stat()
        found.append(
            ArchiveFile(
                path=file.relative_to(data).as_posix(),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )
    return sorted(found, key=lambda archive: archive.path)


def file_sha256(file: Path) -> str:
    """The SHA-256 of a file's contents, in hex."""
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def hash_archives(data: Path, archives: Iterable[ArchiveFile]) -> list[HashedArchive]:
    """Each archive with its SHA-256, read from `data`."""
    return [
        HashedArchive(
            path=archive.path,
            size=archive.size,
            mtime_ns=archive.mtime_ns,
            sha256=file_sha256(data / archive.path),
        )
        for archive in archives
    ]


def build_id(archives: Iterable[HashedArchive]) -> str:
    """The build id of a set of archives, whatever order they come in."""
    digest = hashlib.sha256()
    for archive in sorted(archives, key=lambda each: each.path):
        digest.update(f"{archive.path}\0{archive.size}\0{archive.sha256}\n".encode())
    return digest.hexdigest()[:BUILD_ID_LENGTH]
