"""
`decode_canvas`: a canvas's bytes to RGBA pixels, for each format and layout.

The expected pixels are worked out by hand from each format's definition, not
by the decoder: a BGRA4444 nibble `n` is `17 * n`, an RGB565 channel repeats
its high bits into its low ones, and DXT5 and BC7 blocks are built bit by bit
below, with the values their specifications give.
"""

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest

from game_data.archive import (
    CanvasNode,
    CanvasRef,
    CorruptArchive,
    Pixels,
    UnsupportedFormat,
    WzArchive,
    decode_canvas,
)
from tests.test_game_data import wz_writer as w

ARCHIVE = Path("Data/Mob/_Canvas/_Canvas.wz")
WHERE = {"archive": ARCHIVE, "image": "0100100.img", "node": "stand/0"}


def ref(
    width: int, height: int, data: bytes, pixel_format: int, scale: int = 0
) -> CanvasRef:
    return CanvasRef(
        offset=0,
        length=len(data),
        format=pixel_format,
        scale=scale,
        width=width,
        height=height,
    )


def decode(
    width: int, height: int, raw: bytes, pixel_format: int, scale: int = 0
) -> Pixels:
    data = zlib.compress(raw)
    return decode_canvas(data, ref(width, height, data, pixel_format, scale), **WHERE)


def rgba(rows: list[list[tuple[int, int, int, int]]]) -> Pixels:
    return np.array(rows, dtype=np.uint8)


# --- the formats -----------------------------------------------------------


def test_bgra4444_spreads_each_nibble_over_a_byte() -> None:
    def pixel(r: int, g: int, b: int, a: int) -> bytes:
        return struct.pack("<H", b | g << 4 | r << 8 | a << 12)

    raw = pixel(15, 0, 0, 15) + pixel(0, 15, 0, 8) + pixel(0, 0, 15, 0)
    raw += pixel(1, 2, 3, 4)

    pixels = decode(2, 2, raw, 1)

    assert pixels.dtype == np.uint8
    np.testing.assert_array_equal(
        pixels,
        rgba(
            [
                [(255, 0, 0, 255), (0, 255, 0, 136)],
                [(0, 0, 255, 0), (17, 34, 51, 68)],
            ]
        ),
    )


def test_bgra8888_reorders_each_pixel_to_rgba() -> None:
    raw = bytes([1, 2, 3, 4, 10, 20, 30, 40, 0, 0, 255, 128])

    np.testing.assert_array_equal(
        decode(3, 1, raw, 2),
        rgba([[(3, 2, 1, 4), (30, 20, 10, 40), (255, 0, 0, 128)]]),
    )


def test_rgb565_is_opaque_and_repeats_high_bits_into_low_ones() -> None:
    raw = struct.pack("<4H", 0xF800, 0x07E0, 0x001F, 0x8410)

    np.testing.assert_array_equal(
        decode(2, 2, raw, 513),
        rgba(
            [
                [(255, 0, 0, 255), (0, 255, 0, 255)],
                [(0, 0, 255, 255), (132, 130, 132, 255)],
            ]
        ),
    )


def test_a_scaled_canvas_stores_one_pixel_per_square_and_is_cropped() -> None:
    # 20x17 at scale 4: 2x2 stored pixels, each standing for 16x16.
    raw = struct.pack("<4H", 0xF800, 0x07E0, 0x001F, 0xFFFF)

    pixels = decode(20, 17, raw, 513, scale=4)

    assert pixels.shape == (17, 20, 4)
    red, green, blue, white = (
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 255, 255),
    )
    assert (pixels[:16, :16] == red).all()
    assert (pixels[:16, 16:] == green).all()
    assert (pixels[16:, :16] == blue).all()
    assert (pixels[16:, 16:] == white).all()


DXT5_ALPHAS = [255, 0, 218, 182, 145, 109, 72, 36]
DXT5_COLORS = [(255, 0, 0), (0, 0, 255), (170, 0, 85), (85, 0, 170)]


def dxt5_block(alpha0: int, alpha1: int, alpha_index: list[int]) -> bytes:
    """Red and blue endpoints; pixel `i` takes colour index `i % 4`."""
    alpha_bits = sum(index << 3 * i for i, index in enumerate(alpha_index))
    color_bits = sum((i % 4) << 2 * i for i in range(16))
    return (
        bytes([alpha0, alpha1])
        + alpha_bits.to_bytes(6, "little")
        + struct.pack("<HHI", 0xF800, 0x001F, color_bits)
    )


def test_dxt5_interpolates_eight_alphas_and_four_colours() -> None:
    block = dxt5_block(255, 0, [i % 8 for i in range(16)])

    pixels = decode(4, 4, block, 2050)

    expected = [(*DXT5_COLORS[i % 4], DXT5_ALPHAS[i % 8]) for i in range(16)]
    np.testing.assert_array_equal(pixels.reshape(16, 4), np.array(expected))


def test_dxt5_with_alpha0_not_above_alpha1_has_six_alphas_then_0_and_255() -> None:
    block = dxt5_block(0, 255, [2, 6, 7, 0] + [0] * 12)

    pixels = decode(4, 4, block, 2050)

    assert list(pixels[0, :, 3]) == [51, 0, 255, 0]


def test_block_formats_lay_blocks_row_by_row_and_crop_partial_ones() -> None:
    opaque = dxt5_block(255, 255, [0] * 16)
    clear = dxt5_block(0, 0, [0] * 16)

    pixels = decode(5, 3, opaque + clear, 2050)

    assert pixels.shape == (3, 5, 4)
    assert (pixels[:, :4, 3] == 255).all()
    assert (pixels[:, 4, 3] == 0).all()


class Bits:
    """A 128-bit BC7 block, written low bit first."""

    def __init__(self) -> None:
        self.value = 0
        self.count = 0

    def put(self, value: int, width: int) -> Bits:
        assert 0 <= value < 1 << width
        self.value |= value << self.count
        self.count += width
        return self

    def block(self) -> bytes:
        assert self.count == 128
        return self.value.to_bytes(16, "little")


def test_bc7_mode_6_interpolates_with_four_bit_weights() -> None:
    bits = Bits().put(1 << 6, 7)
    for _ in range(4):  # red, green, blue, alpha
        bits.put(0, 7).put(127, 7)
    bits.put(0, 1).put(1, 1)  # p-bits: the endpoints are 0 and 255
    bits.put(0, 3)  # pixel 0 is the anchor: its index has one bit less
    for index in range(1, 16):
        bits.put(index, 4)

    pixels = decode(4, 4, bits.block(), 4098)

    ramp = [0, 16, 36, 52, 68, 84, 104, 120, 135, 151, 171, 187, 203, 219, 239, 255]
    np.testing.assert_array_equal(pixels.reshape(16, 4), np.repeat([ramp], 4, 0).T)


def test_bc7_mode_1_splits_pixels_by_partition_with_shared_p_bits() -> None:
    # Partition 13: the top two rows are subset 0, the bottom two subset 1,
    # whose anchor is pixel 15.
    bits = Bits().put(0b10, 2).put(13, 6)
    for subset0, subset1 in (((63, 63), (0, 0)), ((0, 0), (63, 0)), ((0, 0), (0, 63))):
        for end in (*subset0, *subset1):
            bits.put(end, 6)
    bits.put(1, 1).put(0, 1)
    bits.put(0, 2)
    for _ in range(1, 15):
        bits.put(0, 3)
    bits.put(3, 2)

    pixels = decode(4, 4, bits.block(), 4098).reshape(16, 4)

    assert (pixels[:8] == (255, 2, 2, 255)).all()
    assert (pixels[8:15] == (0, 253, 0, 255)).all()
    assert tuple(pixels[15]) == (0, 146, 107, 255)


def test_bc7_mode_2_splits_pixels_across_three_subsets() -> None:
    bits = Bits().put(0b100, 3).put(0, 6)
    for subsets in (
        ((0, 0), (31, 31), (0, 0)),
        ((0, 0),) * 3,
        ((0, 0), (0, 0), (31, 31)),
    ):
        for subset in subsets:
            for end in subset:
                bits.put(end, 5)
    bits.put(0, 29)

    pixels = decode(4, 4, bits.block(), 4098).reshape(16, 4)

    colors = {"0": (0, 0, 0, 255), "1": (255, 0, 0, 255), "2": (0, 0, 255, 255)}
    expected = [colors[subset] for subset in "0011001102212222"]
    np.testing.assert_array_equal(pixels, np.array(expected))


def test_bc7_rotation_swaps_a_channel_with_alpha() -> None:
    bits = Bits().put(1 << 5, 6).put(1, 2)  # mode 5, rotation 1: red and alpha
    for low, high in ((127, 127), (0, 0), (0, 0)):
        bits.put(low, 7).put(high, 7)
    bits.put(64, 8).put(64, 8)
    bits.put(0, 31).put(0, 31)

    pixels = decode(4, 4, bits.block(), 4098)

    assert (pixels.reshape(16, 4) == (64, 0, 0, 255)).all()


def test_a_bc7_block_with_no_mode_is_transparent_black() -> None:
    pixels = decode(4, 4, bytes(16), 4098)

    assert (pixels == 0).all()


# --- layouts and errors ----------------------------------------------------


def test_an_unfinished_zlib_stream_decodes_as_the_client_stores_it() -> None:
    raw = bytes([1, 2, 3, 4, 5, 6, 7, 8])
    compressor = zlib.compressobj()
    data = compressor.compress(raw) + compressor.flush(zlib.Z_SYNC_FLUSH)

    pixels = decode_canvas(data, ref(2, 1, data, 2), **WHERE)

    np.testing.assert_array_equal(pixels, rgba([[(3, 2, 1, 4), (7, 6, 5, 8)]]))


def test_zlib_split_into_length_prefixed_blocks_decodes() -> None:
    raw = bytes(range(16))
    stream = zlib.compress(raw)
    data = b"".join(
        struct.pack("<i", len(part)) + part for part in (stream[:5], stream[5:])
    )

    pixels = decode_canvas(data, ref(4, 1, data, 2), **WHERE)

    np.testing.assert_array_equal(
        pixels,
        rgba([[(2, 1, 0, 3), (6, 5, 4, 7), (10, 9, 8, 11), (14, 13, 12, 15)]]),
    )


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"\x00\x01\x02\x03\x04\x05", id="neither"),
        pytest.param(struct.pack("<i", 2) + b"\x00\x00", id="blocks-not-zlib"),
        pytest.param(struct.pack("<i", 9) + b"\x78\x9c", id="block-past-the-end"),
    ],
)
def test_data_in_neither_layout_raises_naming_where_and_the_format(
    data: bytes,
) -> None:
    with pytest.raises(CorruptArchive) as raised:
        decode_canvas(data, ref(1, 1, data, 2), **WHERE)

    error = raised.value
    assert (error.archive, error.image, error.node) == (
        str(ARCHIVE),
        "0100100.img",
        "stand/0",
    )
    assert "pixel format 2" in error.reason
    assert "neither a zlib stream nor zlib blocks" in error.reason


@pytest.mark.parametrize("raw", [bytes(7), bytes(9)], ids=["short", "long"])
def test_pixel_data_of_the_wrong_size_raises(raw: bytes) -> None:
    data = zlib.compress(raw)

    with pytest.raises(CorruptArchive, match="inflates to .* but the format needs 8"):
        decode_canvas(data, ref(2, 1, data, 2), **WHERE)


def test_an_unsupported_format_raises_naming_where_and_the_format_number() -> None:
    data = zlib.compress(bytes(4))

    with pytest.raises(UnsupportedFormat) as raised:
        decode_canvas(data, ref(1, 1, data, 3), **WHERE)

    error = raised.value
    assert (error.archive, error.image, error.node) == (
        str(ARCHIVE),
        "0100100.img",
        "stand/0",
    )
    assert "pixel format 3" in error.reason


def test_an_archive_decodes_a_canvas_it_holds(tmp_path: Path) -> None:
    raw = bytes([1, 2, 3, 4])
    path = tmp_path / "Mob.wz"
    w.write_archive(
        path,
        w.Dir(
            "",
            [
                w.Img(
                    "0100100.img",
                    [w.Canvas("0", 1, 1, zlib.compress(raw), format=2)],
                )
            ],
        ),
    )
    archive = WzArchive.open(path)
    entry = archive.root.images["0100100.img"]
    node = archive.parse(entry)["0"]
    assert isinstance(node, CanvasNode)

    pixels = archive.pixels(entry, node.canvas, "0")

    np.testing.assert_array_equal(pixels, rgba([[(3, 2, 1, 4)]]))
