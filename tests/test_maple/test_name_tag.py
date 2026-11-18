"""
`maple.screen.name_tag` on drawn name tags: made-up glyphs, a dark box, and
the client's upscale done by OpenCV. No frame, no client pixels. The real
frames are `test_name_tag_frames.py`.
"""

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from maple.screen.font import NAME_TAG, UNREAD, GlyphSet
from maple.screen.name_tag import (
    NAME_TAGS,
    OFFSETS,
    UNSCALED_WHITE,
    _blend,
    horizontal_scales,
    read_name_tag,
    unscale,
)


def glyph(rows: list[str]) -> NDArray[np.bool_]:
    return np.array([[c == "#" for c in row] for row in rows])


# Each 11 rows, as a tag's cell: a capital's top on row 0, the baseline under
# row 8, a descender on rows 9 and 10.
GLYPHS = {
    "A": glyph(
        [
            "..#..",
            ".#.#.",
            ".#.#.",
            "#...#",
            "#####",
            "#...#",
            "#...#",
            "#...#",
            "#...#",
            ".....",
            ".....",
        ]
    ),
    "b": glyph(
        [
            "#...",
            "#...",
            "#...",
            "###.",
            "#..#",
            "#..#",
            "#..#",
            "#..#",
            "###.",
            "....",
            "....",
        ]
    ),
    "o": glyph(
        [
            "....",
            "....",
            "....",
            ".##.",
            "#..#",
            "#..#",
            "#..#",
            "#..#",
            ".##.",
            "....",
            "....",
        ]
    ),
    "p": glyph(
        [
            "....",
            "....",
            "....",
            "###.",
            "#..#",
            "#..#",
            "#..#",
            "#..#",
            "###.",
            "#...",
            "#...",
        ]
    ),
}
NOT_HARVESTED = glyph(
    [
        "#####",
        "....#",
        "...#.",
        "...#.",
        "..#..",
        "..#..",
        ".#...",
        ".#...",
        "#####",
        ".....",
        ".....",
    ]
)
SET = GlyphSet(NAME_TAG, GLYPHS)

BACKGROUND = (150, 170, 130)
BOX = (40, 35, 30)
WHITE = (255, 255, 255)


def blank(width: int = 160, height: int = 40) -> NDArray[np.uint8]:
    image = np.empty((height, width, 3), np.uint8)
    image[:] = BACKGROUND
    return image


def draw_tag(image: NDArray[np.uint8], text: str, left: int, top: int = 12) -> None:
    """A tag as the client draws one at 1:1: `text`'s glyphs in pure white,
    a column apart, their cell's top at `top`, on a dark box 3 px wider all
    round (`font.NAME_TAG`)."""
    masks = [NOT_HARVESTED if c == "?" else GLYPHS[c] for c in text]
    width = sum(m.shape[1] for m in masks) + len(masks) - 1
    image[top - 3 : top + 14, left - 3 : left + width + 3] = BOX
    x = left
    for mask in masks:
        h, w = mask.shape
        image[top : top + h, x : x + w][mask] = WHITE
        x += w + 1


def upscaled(
    image: NDArray[np.uint8], size: tuple[int, int], offset: tuple[float, float]
) -> NDArray[np.uint8]:
    """`image`, drawn at 1:1 in a play area of 1366x768, upscaled as a client
    of `size` draws it (bilinear), shifted by `offset` play-area px."""
    kx, ky = size[0] / 1366, size[1] / 768
    height, width = image.shape[:2]
    to_play_area = np.array(
        [
            [1 / kx, 0, 0.5 / kx - 0.5 + offset[0]],
            [0, 1 / ky, 0.5 / ky - 0.5 + offset[1]],
        ]
    )
    return np.asarray(
        cv2.warpAffine(
            image,
            to_play_area,
            (round(width * kx), round(height * ky)),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        ),
        np.uint8,
    )


def test_the_reader_names_the_name_tag_glyphs() -> None:
    assert NAME_TAGS.glyph_sets == (NAME_TAG.name,)


@pytest.mark.parametrize("size", [(800, 600), (1024, 768), (1366, 768)])
def test_a_tag_drawn_1_to_1_reads_as_its_glyphs(size: tuple[int, int]) -> None:
    image = blank()
    draw_tag(image, "AbpA", 40)
    assert read_name_tag(SET, image, size) == "AbpA"


def test_a_letter_with_no_glyph_reads_unread() -> None:
    image = blank()
    draw_tag(image, "A?bA", 40)
    assert read_name_tag(SET, image, (1366, 768)) == f"A{UNREAD}bA"


def test_a_name_with_no_tall_letter_reads_from_its_cell() -> None:
    """Its ink starts 3 rows down its cell: the cell is placed where its
    letters read."""
    image = blank()
    draw_tag(image, "opoo", 40)
    assert read_name_tag(SET, image, (1366, 768)) == "opoo"


def test_the_tag_nearest_the_middle_is_read() -> None:
    image = blank(width=200)
    draw_tag(image, "AAAA", 10)
    draw_tag(image, "bbbb", 90)
    draw_tag(image, "oooo", 160)
    assert read_name_tag(SET, image, (1366, 768)) == "bbbb"


def test_no_tag_reads_nothing() -> None:
    assert read_name_tag(SET, blank(), (1366, 768)) == ""


def test_a_client_size_not_measured_reads_nothing() -> None:
    image = blank()
    draw_tag(image, "AbpA", 40)
    assert read_name_tag(SET, image, (1600, 900)) == ""


@pytest.mark.parametrize("offset", [(0.0, 0.0), (0.3, -0.2), (-0.45, 0.4), (0.1, 0.25)])
def test_an_upscaled_tag_reads_as_drawn_wherever_it_sits(
    offset: tuple[float, float],
) -> None:
    image = blank()
    draw_tag(image, "AbpA", 40)
    client = upscaled(image, (1920, 1080), offset)
    assert read_name_tag(SET, client, (1920, 1080)) == "AbpA"


def test_an_upscaled_tag_with_no_tall_letter_reads_too() -> None:
    image = blank()
    draw_tag(image, "opoo", 40)
    client = upscaled(image, (1920, 1080), (0.2, 0.1))
    assert read_name_tag(SET, client, (1920, 1080)) == "opoo"


def test_an_upscaled_letter_with_no_glyph_reads_unread() -> None:
    image = blank()
    draw_tag(image, "A?bA", 40)
    client = upscaled(image, (1920, 1080), (-0.2, 0.3))
    assert read_name_tag(SET, client, (1920, 1080)) == f"A{UNREAD}bA"


def test_a_tag_upscaled_by_the_vertical_scale_on_both_axes_reads_too() -> None:
    """On some captures the client upscales by its height over the play
    area's on both axes (`horizontal_scales`)."""
    image = blank()
    draw_tag(image, "AbpA", 40)
    client = upscaled(image, (1920, 1080), (0.3, 0.0))
    stretched = np.asarray(
        cv2.resize(
            image,
            (round(160 * 1080 / 768), client.shape[0]),
            interpolation=cv2.INTER_LINEAR,
        ),
        np.uint8,
    )
    assert read_name_tag(SET, stretched, (1920, 1080)) == "AbpA"


def test_the_horizontal_scales_are_the_width_s_and_the_height_s() -> None:
    assert horizontal_scales((1920, 1080)) == (1920 / 1366, 1080 / 768)
    assert horizontal_scales((1366, 768)) == (1.0,)
    assert horizontal_scales((1600, 900)) == ()


@pytest.mark.parametrize(
    ("offset_x", "offset_y"), [(-0.5, 0.0), (0.1, -0.3), (0.4, 0.2), (-0.2, -0.5)]
)
def test_unscaling_solves_a_bilinear_upscale_exactly(
    offset_x: float, offset_y: float
) -> None:
    assert {offset_x, offset_y} <= set(OFFSETS)
    kx, ky = 1920 / 1366, 1080 / 768
    ay, first_row = _blend(20, ky, offset_y)
    ax, first_column = _blend(42, kx, offset_x)
    rng = np.random.default_rng(7)
    tag = np.where(rng.random((ay.shape[1], ax.shape[1])) < 0.4, 255.0, 40.0)

    solved, row, column, scale = unscale(ay @ tag @ ax.T, (kx, ky), ky)

    assert (scale, row, column) == (kx, first_row, first_column)
    assert solved.shape == tag.shape
    assert ((solved >= UNSCALED_WHITE) == (tag == 255)).all()
