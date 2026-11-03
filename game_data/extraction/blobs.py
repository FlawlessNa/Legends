"""
The blob store: the bytes of the client's font, one file per blob, shared by
every extraction.

The raw layer keeps a raw-data node only as a length and a SHA-256
(`raw`). The bytes of the ones under `UI/Font/` are written here, at
`blobs/<sha256>`, since the client's font is what the bot reads AP with. A
blob's name is the SHA-256 of its bytes, so it is checked when read back.

A blob is written once, to a temporary file renamed into place, so a run that
dies never leaves a truncated blob under a real name.
"""

import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from .images import is_name
from .raw import Json

FONT = "UI/Font/"
RAW_DATA = "raw_data"


class BlobStore:
    """
    The `blobs/` folder of a store.

    :param folder: The folder, created when the first blob is written.
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, name: str) -> Path:
        """Where the blob `name` is, or would be."""
        return self.folder / name

    def has(self, name: str) -> bool:
        return self.path(name).is_file()

    def write(self, data: bytes) -> bool:
        """
        Writes a blob, named by its SHA-256, unless the store has it.

        :return: Whether it was written.
        """
        target = self.path(hashlib.sha256(data).hexdigest())
        if target.is_file():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        return True

    def files(self) -> Iterator[tuple[str | None, Path]]:
        """
        Every file in the store, with the blob it holds, or `None` for a file
        that isn't a blob, such as a temporary file a dead run left behind.
        """
        if not self.folder.is_dir():
            return
        for file in self.folder.iterdir():
            yield (file.name if file.is_file() and is_name(file.name) else None), file


def font_blob_names(tree: Json) -> set[str]:
    """The SHA-256 of every raw-data node in an image's JSON tree."""
    found: set[str] = set()
    pending = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            sha256 = node.get("sha256")
            if node.get("$type") == RAW_DATA and isinstance(sha256, str):
                found.add(sha256)
            pending.extend(node.values())
    return found


def referenced_blobs(raw: Path) -> set[str]:
    """The blobs the `UI/Font/` trees of a raw layer name."""
    with closing(sqlite3.connect(f"{raw.as_uri()}?mode=ro", uri=True)) as database:
        rows = database.execute(
            "SELECT tree FROM images WHERE substr(path, 1, ?) = ?", (len(FONT), FONT)
        ).fetchall()
    found: set[str] = set()
    for (tree,) in rows:
        found |= font_blob_names(json.loads(tree))
    return found
