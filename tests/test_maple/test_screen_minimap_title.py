"""
The minimap banner's title on synthetic frames: the minimap of
`test_screen_minimap`, with made-up glyphs drawn white on a plain banner where
the client draws its title. No client pixels, no harvested glyphs.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from maple.screen.font import MINIMAP_TITLE, GlyphSet
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MinimapReader
from maple.screen.minimap_title import MARK, MinimapTitleReader
from maple.screen.sprites import ReaderSprites
from tests.test_maple.test_screen_minimap import (
    draw_minimap,
    draw_minimised,
    frame,
    occlude,
    screen,
    sprites,
)

ROWS = MINIMAP_TITLE.rows or 0
BANNER_BGR = (204, 187, 153)
"""The banner's colour, (153, 187, 204) in RGB: under `MINIMAP_TITLE`'s ink."""


def _glyph(seed: int) -> np.ndarray:
    """A made-up 5-column glyph, as tall as a line's cell, with ink between
    its cell's top and its baseline and both edge columns inked."""
    rng = np.random.default_rng(seed)
    mask = np.zeros((ROWS, 5), bool)
    mask[0:8] = rng.random((8, 5)) < 0.5
    mask[0:8, 0] = mask[0:8, 4] = True
    return mask


GLYPHS = {char: _glyph(seed) for seed, char in enumerate("ABCabc")}
STREET, NAME = "Ab Ba", "Cab"
TITLE = f"{STREET}: {NAME}"
TITLES = (TITLE, "Ab Ba: Bac", "Cc: Ab")
FRAME_AT = (250, 20)


def title_sprites() -> ReaderSprites:
    s = sprites()
    s.glyph_sets[MINIMAP_TITLE.name] = GlyphSet(MINIMAP_TITLE, GLYPHS)
    return s


def draw_line(pixels: np.ndarray, text: str, x: int, top: int) -> None:
    """`text` in `GLYPHS`, white, its cell's top at `top`: letters a column
    apart, words four."""
    for char in text:
        if char == " ":
            x += 3
            continue
        mask = GLYPHS[char]
        cell = pixels[top : top + ROWS, x : x + mask.shape[1]]
        cell[mask] = 255
        x += mask.shape[1] + 1


def draw_title(
    pixels: np.ndarray,
    lines: tuple[str, ...] = (STREET, NAME),
    at: tuple[int, int] = FRAME_AT,
    first_row: int = 30,
) -> None:
    """The banner beside the mark, plain, with `lines` 14 rows apart from
    `first_row` below the frame's top (`at`)."""
    x, y = at
    pixels[y + MARK.top : y + MARK.bottom, x + MARK.right : x + 126] = BANNER_BGR
    for i, text in enumerate(lines):
        draw_line(pixels, text, x + MARK.right + 4, y + first_row + 14 * i)


def banner_frame(lines: tuple[str, ...] = (STREET, NAME), first_row: int = 30) -> Frame:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT)
    draw_title(pixels, lines, first_row=first_row)
    return frame(pixels)


def title_reader(titles: tuple[str, ...] = TITLES) -> MinimapTitleReader:
    s = title_sprites()
    return MinimapTitleReader(s, MinimapReader(s, FrameCheck(s)), titles)


@pytest.mark.parametrize("first_row", [30, 31])
def test_the_title_reads_as_the_catalogues_name(first_row: int) -> None:
    """Wherever the lines sit beside the mark: on frame set v2, a row apart
    between the two maps."""
    reading = title_reader().read(banner_frame(first_row=first_row))

    assert reading.status is Status.READ
    assert reading.value == TITLE


def test_spaces_are_left_out_of_the_comparison() -> None:
    """The catalogue's spelling comes back, however the gaps were read."""
    reading = title_reader(("AbBa: Cab",)).read(banner_frame())

    assert reading.value == "AbBa: Cab"


def test_a_title_no_map_is_called_is_unsure() -> None:
    reading = title_reader(("Cc: Ab",)).read(banner_frame())

    assert reading.status is Status.UNSURE
    assert "no map is called" in reading.detail


def test_a_letter_not_harvested_is_unsure_never_a_title_with_it_missing() -> None:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT)
    draw_title(pixels)
    # A sixth, unknown glyph after the street.
    x, y = FRAME_AT
    pixels[y + 30 : y + 38, x + MARK.right + 40 : x + MARK.right + 43] = 255

    reading = title_reader().read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert "harvested" in reading.detail


@pytest.mark.parametrize("lines", [(STREET,), (STREET, NAME, "Ab")])
def test_anything_but_two_lines_is_unsure(lines: tuple[str, ...]) -> None:
    reading = title_reader().read(banner_frame(lines))

    assert reading.status is Status.UNSURE
    assert f"{len(lines)} line(s)" in reading.detail


def test_lines_that_run_into_each_other_are_unsure() -> None:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT)
    draw_title(pixels)
    x, y = FRAME_AT
    # Ink joining the two lines' rows, in one column.
    pixels[y + 30 : y + 50, x + MARK.right + 4] = 255

    reading = title_reader().read(frame(pixels))

    assert reading.status is Status.UNSURE


def test_the_look_without_the_banner_is_unsure() -> None:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT, banner=False)

    reading = title_reader().read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert "no banner" in reading.detail


def test_a_minimised_minimap_is_unsure() -> None:
    pixels = screen()
    draw_minimised(pixels, *FRAME_AT)

    reading = title_reader().read(frame(pixels))

    assert reading.status is Status.UNSURE


def test_no_minimap_is_the_minimaps_own_status() -> None:
    reading = title_reader().read(frame(screen()))

    assert reading.status is Status.ABSENT


def test_a_covered_minimap_is_the_minimaps_own_status() -> None:
    pixels = screen()
    draw_minimap(pixels, *FRAME_AT)
    draw_title(pixels)
    x, y = FRAME_AT
    occlude(pixels, x + 110, y, 40, 30)

    reading = title_reader().read(frame(pixels))

    assert reading.status is Status.COVERED
