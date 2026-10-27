"""
Decodes a canvas's pixels to an RGBA array.

`decode_canvas` takes the bytes a `CanvasRef` points at and returns a
`(height, width, 4)` array of `uint8`, red, green, blue, alpha.

**Layouts.** The pixel data is compressed in one of two layouts:

- **zlib**: the bytes are one zlib stream. Classic flushes its streams without
  finishing them, so the decoder checks the inflated length, not the end of
  the stream.
- **Blocks**: an `int32` length then that many bytes, repeated to the end. The
  blocks, joined, are the zlib stream. WZ encrypts each block with the
  archive's key, which in Classic is zero, as it is for strings. Classic stores
  no canvas this way, so only the test writer exercises it.

Anything else raises `CorruptArchive`, as does a stream that inflates to more
or fewer bytes than the format needs.

**Formats.** Every pixel format Classic uses:

| format | name     | stored as                                         |
| ------ | -------- | ------------------------------------------------- |
| 1      | BGRA4444 | 2 bytes a pixel                                   |
| 2      | BGRA8888 | 4 bytes a pixel                                   |
| 513    | RGB565   | 2 bytes a pixel, opaque                           |
| 2050   | DXT5     | 16 bytes a 4x4 block (BC3)                        |
| 4098   | BC7      | 16 bytes a 4x4 block                              |

Any other raises `UnsupportedFormat`, naming the format number.

**Scale.** The byte after the format (`CanvasRef.scale`) is a power of two:
the data holds `ceil(width / 2**scale)` by `ceil(height / 2**scale)` pixels,
each standing for a square of `2**scale` pixels. Classic uses it only with
RGB565 at scale 4, which older tools call format 517 (513 + 4).
"""

import struct
import zlib
from collections.abc import Buffer, Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from .errors import CorruptArchive, UnsupportedFormat
from .nodes import CanvasRef
from .reader import BadFormat

type Pixels = NDArray[np.uint8]
type _Ints = NDArray[np.int64]

# The second byte of a zlib header whose first byte is 0x78 (deflate, 32K
# window), at each compression level, as the client writes them.
_ZLIB_LEVELS = frozenset({0x01, 0x5E, 0x9C, 0xDA})
_BLOCK_LENGTH = struct.Struct("<i")


def decode_canvas(
    data: Buffer,
    ref: CanvasRef,
    *,
    archive: Path | str,
    image: str,
    node: str,
) -> Pixels:
    """
    A canvas's pixels.

    :param data: The `ref.length` bytes at `ref.offset`.
    :param ref: The canvas.
    :param archive: The file the canvas is in, for errors.
    :param image: The image it is in, for errors.
    :param node: Its path inside the image, for errors.
    :return: `(ref.height, ref.width, 4)`, RGBA.
    :raises UnsupportedFormat: The pixel format isn't one of the above.
    :raises CorruptArchive: The data isn't in either layout, or doesn't inflate
        to the size the format needs.
    """
    pixel_format = _FORMATS.get(ref.format)
    if pixel_format is None:
        raise UnsupportedFormat(
            archive, image, node, f"pixel format {ref.format} isn't supported"
        )
    step = 1 << ref.scale
    width = -(-ref.width // step)
    height = -(-ref.height // step)
    size = pixel_format.size(width, height)
    try:
        raw = _inflate(bytes(data), size)
    except BadFormat as error:
        raise CorruptArchive(
            archive, image, node, f"pixel format {ref.format}: {error}"
        ) from error
    pixels = pixel_format.decode(raw, width, height)
    if step > 1:
        pixels = pixels.repeat(step, axis=0).repeat(step, axis=1)
        pixels = pixels[: ref.height, : ref.width]
    return np.ascontiguousarray(pixels)


def _inflate(data: bytes, size: int) -> bytes:
    stream = data if _is_zlib(data) else _join_blocks(data)
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(stream)
    except zlib.error as error:
        raise BadFormat(f"the pixel data doesn't inflate: {error}") from error
    if inflater.unused_data:
        raise BadFormat(
            f"{len(inflater.unused_data)} bytes follow the end of the zlib stream"
        )
    if len(raw) != size:
        raise BadFormat(
            f"the pixel data inflates to {len(raw)} bytes, but the format needs {size}"
        )
    return raw


def _is_zlib(data: bytes) -> bool:
    return len(data) >= 2 and data[0] == 0x78 and data[1] in _ZLIB_LEVELS


def _join_blocks(data: bytes) -> bytes:
    neither = "the pixel data is neither a zlib stream nor zlib blocks"
    blocks: list[bytes] = []
    pos = 0
    while pos < len(data):
        if pos + _BLOCK_LENGTH.size > len(data):
            raise BadFormat(neither)
        (length,) = _BLOCK_LENGTH.unpack_from(data, pos)
        pos += _BLOCK_LENGTH.size
        if length <= 0 or pos + length > len(data):
            raise BadFormat(neither)
        blocks.append(data[pos : pos + length])
        pos += length
    stream = b"".join(blocks)
    if not _is_zlib(stream):
        raise BadFormat(neither)
    return stream


# --- formats ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Format:
    """
    :ivar size: The bytes `width` by `height` pixels take.
    :ivar decode: Those bytes to `(height, width, 4)` RGBA.
    """

    size: Callable[[int, int], int]
    decode: Callable[[bytes, int, int], Pixels]


def _blocks(width: int, height: int) -> int:
    return -(-width // 4) * -(-height // 4)


def _bgra4444(raw: bytes, width: int, height: int) -> Pixels:
    packed = np.frombuffer(raw, dtype="<u2").reshape(height, width)
    nibbles = [(packed >> shift) & 0xF for shift in (8, 4, 0, 12)]
    return (np.stack(nibbles, axis=-1) * 17).astype(np.uint8)


def _bgra8888(raw: bytes, width: int, height: int) -> Pixels:
    bgra = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4)
    return bgra[..., [2, 1, 0, 3]]


def _rgb565(raw: bytes, width: int, height: int) -> Pixels:
    packed = np.frombuffer(raw, dtype="<u2").reshape(height, width).astype(np.int64)
    rgb = _expand_565(packed)
    alpha = np.full((height, width, 1), 255, dtype=np.int64)
    return np.concatenate([rgb, alpha], axis=-1).astype(np.uint8)


def _expand_565(packed: _Ints) -> _Ints:
    """RGB565 values to `(..., 3)` 8-bit RGB, replicating the high bits."""
    red = (packed >> 11) & 0x1F
    green = (packed >> 5) & 0x3F
    blue = packed & 0x1F
    return np.stack(
        [
            (red << 3) | (red >> 2),
            (green << 2) | (green >> 4),
            (blue << 3) | (blue >> 2),
        ],
        axis=-1,
    )


def _tile(blocks: NDArray[np.integer], width: int, height: int) -> Pixels:
    """`(n, 16, 4)` blocks, row by row, to `(height, width, 4)` pixels."""
    across = -(-width // 4)
    down = -(-height // 4)
    grid = blocks.astype(np.uint8).reshape(down, across, 4, 4, 4)
    pixels = grid.transpose(0, 2, 1, 3, 4).reshape(down * 4, across * 4, 4)
    return pixels[:height, :width]


def _dxt5(raw: bytes, width: int, height: int) -> Pixels:
    blocks = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 16).astype(np.int64)
    shifts = np.arange(16)

    alpha0 = blocks[:, 0:1]
    alpha1 = blocks[:, 1:2]
    alpha_bits = _little_endian(blocks[:, 2:8])
    alpha_index = (alpha_bits[:, None] >> (3 * shifts)) & 7
    steps = np.arange(1, 7)
    eight = ((7 - steps) * alpha0 + steps * alpha1) // 7
    six = ((5 - steps[:4]) * alpha0 + steps[:4] * alpha1) // 5
    six = np.concatenate([six, np.zeros_like(alpha0), np.full_like(alpha0, 255)], 1)
    alphas = np.concatenate([alpha0, alpha1, np.where(alpha0 > alpha1, eight, six)], 1)

    color0 = _expand_565(_little_endian(blocks[:, 8:10]))
    color1 = _expand_565(_little_endian(blocks[:, 10:12]))
    colors = np.stack(
        [color0, color1, (2 * color0 + color1) // 3, (color0 + 2 * color1) // 3], 1
    )
    color_index = (_little_endian(blocks[:, 12:16])[:, None] >> (2 * shifts)) & 3

    rgb = np.take_along_axis(colors, color_index[:, :, None], axis=1)
    alpha = np.take_along_axis(alphas, alpha_index, axis=1)
    return _tile(np.concatenate([rgb, alpha[:, :, None]], axis=-1), width, height)


def _little_endian(columns: _Ints) -> _Ints:
    """Each row of bytes as one little-endian integer."""
    weights = 1 << (8 * np.arange(columns.shape[1], dtype=np.int64))
    return (columns * weights).sum(axis=1)


# --- BC7 -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Bc7Mode:
    """
    One of BC7's eight block layouts, in the order its fields are stored.

    :ivar subsets: How many endpoint pairs the block's pixels are split across.
    :ivar partition_bits: Bits of the partition number, which picks the split.
    :ivar rotation_bits: Bits naming the channel swapped with alpha.
    :ivar selector_bits: Bits choosing which index set colour uses (mode 4).
    :ivar color_bits: Bits of each endpoint's red, green and blue.
    :ivar alpha_bits: Bits of each endpoint's alpha; 0 means opaque.
    :ivar endpoint_pbits: A low bit of its own for every endpoint.
    :ivar shared_pbits: A low bit shared by each subset's two endpoints.
    :ivar index_bits: Bits of each pixel's first index.
    :ivar index2_bits: Bits of each pixel's second index; 0 means none.
    """

    subsets: int
    partition_bits: int
    rotation_bits: int
    selector_bits: int
    color_bits: int
    alpha_bits: int
    endpoint_pbits: bool
    shared_pbits: bool
    index_bits: int
    index2_bits: int


_BC7_MODES = (
    _Bc7Mode(3, 4, 0, 0, 4, 0, True, False, 3, 0),
    _Bc7Mode(2, 6, 0, 0, 6, 0, False, True, 3, 0),
    _Bc7Mode(3, 6, 0, 0, 5, 0, False, False, 2, 0),
    _Bc7Mode(2, 6, 0, 0, 7, 0, True, False, 2, 0),
    _Bc7Mode(1, 0, 2, 1, 5, 6, False, False, 2, 3),
    _Bc7Mode(1, 0, 2, 0, 7, 8, False, False, 2, 2),
    _Bc7Mode(1, 0, 0, 0, 7, 7, True, False, 4, 0),
    _Bc7Mode(2, 6, 0, 0, 5, 5, True, False, 2, 0),
)

_BC7_WEIGHTS = {
    2: np.array([0, 21, 43, 64]),
    3: np.array([0, 9, 18, 27, 37, 46, 55, 64]),
    4: np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64]),
}

# The subset of each of a block's 16 pixels, row by row, for each partition
# number, from the BC7 specification.
_PARTITIONS_2 = (
    "0011001100110011", "0001000100010001", "0111011101110111", "0001001100110111",
    "0000000100010011", "0011011101111111", "0001001101111111", "0000000100110111",
    "0000000000010011", "0011011111111111", "0000000101111111", "0000000000010111",
    "0001011111111111", "0000000011111111", "0000111111111111", "0000000000001111",
    "0000100011101111", "0111000100000000", "0000000010001110", "0111001100010000",
    "0011000100000000", "0000100011001110", "0000000010001100", "0111001100110001",
    "0011000100010000", "0000100010001100", "0110011001100110", "0011011001101100",
    "0001011111101000", "0000111111110000", "0111000110001110", "0011100110011100",
    "0101010101010101", "0000111100001111", "0101101001011010", "0011001111001100",
    "0011110000111100", "0101010110101010", "0110100101101001", "0101101010100101",
    "0111001111001110", "0001001111001000", "0011001001001100", "0011101111011100",
    "0110100110010110", "0011110011000011", "0110011010011001", "0000011001100000",
    "0100111001000000", "0010011100100000", "0000001001110010", "0000010011100100",
    "0110110010010011", "0011011011001001", "0110001110011100", "0011100111000110",
    "0110110011001001", "0110001100111001", "0111111010000001", "0001100011100111",
    "0000111100110011", "0011001111110000", "0010001011101110", "0100010001110111",
)  # fmt: skip
_PARTITIONS_3 = (
    "0011001102212222", "0001001122112221", "0000200122112211", "0222002200110111",
    "0000000011221122", "0011001100220022", "0022002211111111", "0011001122112211",
    "0000000011112222", "0000111111112222", "0000111122222222", "0012001200120012",
    "0112011201120112", "0122012201220122", "0011011211221222", "0011200122002220",
    "0001001101121122", "0111001120012200", "0000112211221122", "0022002200221111",
    "0111011102220222", "0001000122212221", "0000001101220122", "0000110022102210",
    "0122012200110000", "0012001211222222", "0110122112210110", "0000011012211221",
    "0022110211020022", "0110011020022222", "0011012201220011", "0000200022112221",
    "0000000211221222", "0222002200120011", "0011001200220222", "0120012001200120",
    "0000111122220000", "0120120120120120", "0120201212010120", "0011220011220011",
    "0011112222000011", "0101010122222222", "0000000021212121", "0022112200221122",
    "0022001100220011", "0220122102201221", "0101222222220101", "0000212121212121",
    "0101010101012222", "0222011102220111", "0002111200021112", "0000211221122112",
    "0222011101110222", "0002111211120002", "0110011001102222", "0000000021122112",
    "0110011022222222", "0022001100110022", "0022112211220022", "0000000000002112",
    "0002000100020001", "0222122202221222", "0101222222222222", "0111201122012220",
)  # fmt: skip

# The anchor pixel of the second subset, and of the third, for each partition
# number. The first subset's anchor is always pixel 0. An anchor's index is
# stored one bit short: its top bit is always 0.
_ANCHORS_2 = (
    15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15,
    15, 2, 8, 2, 2, 8, 8, 15, 2, 8, 2, 2, 8, 8, 2, 2,
    15, 15, 6, 8, 2, 8, 15, 15, 2, 8, 2, 2, 2, 15, 15, 6,
    6, 2, 6, 8, 15, 15, 2, 2, 15, 15, 15, 15, 15, 2, 2, 15,
)  # fmt: skip
_ANCHORS_3_SECOND = (
    3, 3, 15, 15, 8, 3, 15, 15, 8, 8, 6, 6, 6, 5, 3, 3,
    3, 3, 8, 15, 3, 3, 6, 10, 5, 8, 8, 6, 8, 5, 15, 15,
    8, 15, 3, 5, 6, 10, 8, 15, 15, 3, 15, 5, 15, 15, 15, 15,
    3, 15, 5, 5, 5, 8, 5, 10, 5, 10, 8, 13, 15, 12, 3, 3,
)  # fmt: skip
_ANCHORS_3_THIRD = (
    15, 8, 8, 3, 15, 15, 3, 8, 15, 15, 15, 15, 15, 15, 15, 8,
    15, 8, 15, 3, 15, 8, 15, 8, 3, 15, 6, 10, 15, 15, 10, 8,
    15, 3, 15, 10, 10, 8, 9, 10, 6, 15, 8, 15, 3, 6, 6, 8,
    15, 3, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 3, 15, 15, 8,
)  # fmt: skip


def _subset_table(rows: tuple[str, ...]) -> _Ints:
    return np.array([[int(digit) for digit in row] for row in rows], dtype=np.int64)


def _anchor_table(*anchors: tuple[int, ...]) -> NDArray[np.bool_]:
    """`(64, 16)`: whether each pixel is an anchor, for each partition."""
    table = np.zeros((64, 16), dtype=np.bool_)
    table[:, 0] = True
    for column in anchors:
        table[np.arange(64), np.array(column)] = True
    return table


_SUBSETS = {
    1: np.zeros((1, 16), dtype=np.int64),
    2: _subset_table(_PARTITIONS_2),
    3: _subset_table(_PARTITIONS_3),
}
_ANCHORS = {
    1: _anchor_table(),
    2: _anchor_table(_ANCHORS_2),
    3: _anchor_table(_ANCHORS_3_SECOND, _ANCHORS_3_THIRD),
}


def _bc7(raw: bytes, width: int, height: int) -> Pixels:
    blocks = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 16)
    bits = np.unpackbits(blocks, axis=1, bitorder="little").astype(np.int64)
    # A block whose first byte is 0 has no mode: the format makes it transparent.
    out = np.zeros((len(blocks), 16, 4), dtype=np.int64)
    first = blocks[:, 0].astype(np.int64)
    for number, mode in enumerate(_BC7_MODES):
        mode_bit = 1 << number
        chosen = np.flatnonzero((first & (2 * mode_bit - 1)) == mode_bit)
        if chosen.size:
            out[chosen] = _Bc7Blocks(bits[chosen], number + 1).decode(mode)
    return _tile(out, width, height)


class _Bc7Blocks:
    """Blocks of one mode, read field by field, all blocks at once."""

    def __init__(self, bits: _Ints, start: int) -> None:
        self._bits = bits
        self._pos = start

    def _take(self, width: int) -> _Ints:
        value = np.zeros(len(self._bits), dtype=np.int64)
        for bit in range(width):
            value |= self._bits[:, self._pos + bit] << bit
        self._pos += width
        return value

    def _indices(self, width: int, anchors: NDArray[np.bool_]) -> _Ints:
        """Each pixel's index, `(n, 16)`, an anchor's one bit short."""
        widths = width - anchors.astype(np.int64)
        starts = self._pos + np.cumsum(widths, axis=1) - widths
        value = np.zeros(widths.shape, dtype=np.int64)
        for bit in range(width):
            at = np.minimum(starts + bit, 127)
            read = np.take_along_axis(self._bits, at, axis=1)
            value |= np.where(bit < widths, read, 0) << bit
        self._pos += 16 * width - int(anchors[0].sum())
        return value

    def decode(self, mode: _Bc7Mode) -> _Ints:
        count = len(self._bits)
        partition = self._take(mode.partition_bits)
        rotation = self._take(mode.rotation_bits)
        selector = self._take(mode.selector_bits)

        endpoints = 2 * mode.subsets
        ends = np.zeros((count, endpoints, 4), dtype=np.int64)
        for channel in range(3):
            for end in range(endpoints):
                ends[:, end, channel] = self._take(mode.color_bits)
        for end in range(endpoints if mode.alpha_bits else 0):
            ends[:, end, 3] = self._take(mode.alpha_bits)

        color_bits, alpha_bits = mode.color_bits, mode.alpha_bits
        if mode.endpoint_pbits or mode.shared_pbits:
            if mode.endpoint_pbits:
                pbits = np.stack([self._take(1) for _ in range(endpoints)], 1)
            else:
                shared = np.stack([self._take(1) for _ in range(mode.subsets)], 1)
                pbits = shared.repeat(2, axis=1)
            ends = (ends << 1) | pbits[:, :, None]
            color_bits += 1
            alpha_bits += 1 if alpha_bits else 0
        ends[:, :, :3] = _expand_bits(ends[:, :, :3], color_bits)
        ends[:, :, 3] = _expand_bits(ends[:, :, 3], alpha_bits) if alpha_bits else 255

        # A one-subset mode reads no partition bits, so `partition` is all 0.
        subsets = _SUBSETS[mode.subsets][partition]
        first = self._indices(mode.index_bits, _ANCHORS[mode.subsets][partition])
        color_weight = alpha_weight = _BC7_WEIGHTS[mode.index_bits][first]
        if mode.index2_bits:
            second = self._indices(mode.index2_bits, _ANCHORS[1][partition])
            second_weight = _BC7_WEIGHTS[mode.index2_bits][second]
            # Mode 4's selector gives colour the second indices, alpha the first.
            swap = (selector == 1)[:, None]
            color_weight = np.where(swap, second_weight, alpha_weight)
            alpha_weight = np.where(swap, alpha_weight, second_weight)

        low = np.take_along_axis(ends, (2 * subsets)[:, :, None], axis=1)
        high = np.take_along_axis(ends, (2 * subsets + 1)[:, :, None], axis=1)
        weight = np.concatenate(
            [np.repeat(color_weight[:, :, None], 3, axis=2), alpha_weight[:, :, None]],
            2,
        )
        pixels = ((64 - weight) * low + weight * high + 32) >> 6

        for number, channel in ((1, 0), (2, 1), (3, 2)):
            rotate = rotation == number
            pixels[rotate, :, channel], pixels[rotate, :, 3] = (
                pixels[rotate, :, 3],
                pixels[rotate, :, channel],
            )
        return pixels


def _expand_bits(value: _Ints, bits: int) -> _Ints:
    """`bits`-bit values to 8 bits, replicating the high bits into the low."""
    return (value << (8 - bits)) | (value >> (2 * bits - 8))


_FORMATS = {
    1: _Format(lambda width, height: 2 * width * height, _bgra4444),
    2: _Format(lambda width, height: 4 * width * height, _bgra8888),
    513: _Format(lambda width, height: 2 * width * height, _rgb565),
    2050: _Format(lambda width, height: 16 * _blocks(width, height), _dxt5),
    4098: _Format(lambda width, height: 16 * _blocks(width, height), _bc7),
}
