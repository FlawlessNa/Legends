"""
The image store: every canvas's pixels, one PNG per image, shared by every
extraction.

An image is at `images/<first two hex digits>/<name>.png`. Its name is the
client's `_hash` when the canvas carries one, and otherwise `pixel_hash`: the
SHA-256 of the decoded pixels, with their width and height, so that two images
of the same bytes in different shapes don't share a name.

An image is written once. One already in the store isn't rewritten, and a new
one is written to a temporary file and renamed, so a run that dies never
leaves a truncated image under a real name.

PNGs are written here with `zlib`, since `cv2` is allowed only in `render/`.
"""

import hashlib
import os
import re
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from game_data.archive import Pixels

SUFFIX = ".png"
_NAME = re.compile(r"[0-9a-f]{64}")
_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 8 bits a channel, colour type 6 (RGBA), deflate, adaptive filtering, no
# interlace.
_RGBA8 = (8, 6, 0, 0, 0)


def pixel_hash(pixels: Pixels) -> str:
    """The name of an image without a `_hash`."""
    height, width, _ = pixels.shape
    digest = hashlib.sha256(struct.pack("<II", width, height))
    digest.update(np.ascontiguousarray(pixels).data)
    return digest.hexdigest()


def is_name(name: str) -> bool:
    """Whether `name` can name an image: 64 lowercase hex digits."""
    return _NAME.fullmatch(name) is not None


def png(pixels: Pixels) -> bytes:
    """`(height, width, 4)` RGBA pixels as a PNG file's bytes."""
    height, width, _ = pixels.shape
    rows = np.zeros((height, width * 4 + 1), dtype=np.uint8)
    rows[:, 1:] = pixels.reshape(height, width * 4)
    return b"".join(
        [
            _SIGNATURE,
            _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, *_RGBA8)),
            _chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)),
            _chunk(b"IEND", b""),
        ]
    )


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data)
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


class ImageStore:
    """
    The `images/` folder of a store.

    :param folder: The folder, created when the first image is written.
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, name: str) -> Path:
        """Where the image `name` is, or would be."""
        return self.folder / name[:2] / f"{name}{SUFFIX}"

    def has(self, name: str) -> bool:
        return self.path(name).is_file()

    def write(self, name: str, pixels: Pixels) -> bool:
        """
        Writes an image unless the store has it.

        :return: Whether it was written.
        """
        target = self.path(name)
        if target.is_file():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
        temporary.write_bytes(png(pixels))
        os.replace(temporary, target)
        return True

    def files(self) -> Iterator[tuple[str | None, Path]]:
        """
        Every file in the store, with the image it holds, or `None` for a file
        that isn't an image, such as a temporary file a dead run left behind.
        """
        if not self.folder.is_dir():
            return
        for bucket in self.folder.iterdir():
            if not bucket.is_dir():
                yield None, bucket
                continue
            for file in bucket.iterdir():
                name = file.name.removesuffix(SUFFIX)
                if file.name.endswith(SUFFIX) and is_name(name):
                    yield name, file
                else:
                    yield None, file
