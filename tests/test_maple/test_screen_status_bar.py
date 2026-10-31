"""
The status bar reader, on synthetic frames: a background the test composes,
sprites it pastes, and occluders it paints. Every sprite is random noise, so
nothing here is client pixels.
"""

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.sprites import GAUGE_LABEL, Profile, ReaderSprites
from maple.screen.status_bar import (
    _EXP_AT,
    _GAUGE_GLYPHS,
    _HP_AT,
    _LEVEL_AT,
    _LEVEL_DIGITS,
    _MP_AT,
    BACKGROUND,
    STATUS_BAR,
    StatusBar,
    StatusBarReader,
)

PROFILE = Profile(job="Hero", game_map="Anywhere")
RNG = np.random.default_rng(309)

# Widths as the client's gauge glyphs: 7 tall, with a few narrower marks.
_WIDTHS = {"]": 4, "%": 7, ".": 3, ",": 4}


def noise(w: int, h: int) -> np.ndarray:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return rgba


def _label() -> np.ndarray:
    return noise(300, 4)


def _background() -> np.ndarray:
    # A frame: opaque at the top and the bottom, open where the numbers go.
    rgba = noise(340, 36)
    rgba[6:28, :, 3] = 0
    return rgba


VECTORS = {_LEVEL_AT: (2, 16), _HP_AT: (60, 16), _MP_AT: (125, 16), _EXP_AT: (190, 16)}
LABEL_ORIGIN = (-20, -9)
BACKGROUND_ORIGIN = (-2, -2)


def build_sprites() -> ReaderSprites:
    canvases: dict[str, Sprite] = {
        GAUGE_LABEL: Sprite(GAUGE_LABEL, _label(), LABEL_ORIGIN),
        BACKGROUND: Sprite(BACKGROUND, _background(), BACKGROUND_ORIGIN),
    }
    for path in _LEVEL_DIGITS.values():
        canvases[path] = Sprite(path, noise(11, 13), (0, 0))
    for char, path in _GAUGE_GLYPHS.items():
        canvases[path] = Sprite(path, noise(_WIDTHS.get(char, 5), 7), (0, 0))
    return ReaderSprites("test", canvases, dict(VECTORS))


SPRITES = build_sprites()
POINT = (30, 20)


def sprite_of(path: str) -> Sprite:
    return SPRITES.canvas(path)


def paste(pixels: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    keep = rgba[:, :, 3] == 255
    h, w = rgba.shape[:2]
    area = pixels[y : y + h, x : x + w]
    area[keep] = rgba[:, :, 2::-1][keep]


def write(
    pixels: np.ndarray, text: str, paths: dict[str, str], at: tuple[int, int]
) -> None:
    x, y = POINT[0] + at[0], POINT[1] + at[1]
    for char in text:
        rgba = sprite_of(paths[char]).rgba
        paste(pixels, rgba, x, y)
        x += rgba.shape[1]


def bar(
    level: str = "123",
    hp: str = "[1500/2000]",
    mp: str = "[300/450]",
    exp: str = "98765[12.34%]",
    size: tuple[int, int] = (440, 100),
) -> np.ndarray:
    pixels = np.full((size[1], size[0], 3), 40, dtype=np.uint8)
    bx, by = POINT[0] - BACKGROUND_ORIGIN[0], POINT[1] - BACKGROUND_ORIGIN[1]
    paste(pixels, sprite_of(BACKGROUND).rgba, bx, by)
    lx, ly = POINT[0] - LABEL_ORIGIN[0], POINT[1] - LABEL_ORIGIN[1]
    paste(pixels, sprite_of(GAUGE_LABEL).rgba, lx, ly)
    write(pixels, level, _LEVEL_DIGITS, VECTORS[_LEVEL_AT])
    write(pixels, hp, _GAUGE_GLYPHS, VECTORS[_HP_AT])
    write(pixels, mp, _GAUGE_GLYPHS, VECTORS[_MP_AT])
    write(pixels, exp, _GAUGE_GLYPHS, VECTORS[_EXP_AT])
    return pixels


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 12.5, True, ok, reason)


@pytest.fixture
def reader() -> StatusBarReader:
    return StatusBarReader(SPRITES, FrameCheck(SPRITES))


def test_the_declaration_names_every_sprite_the_reader_asks_for() -> None:
    assert set(STATUS_BAR.canvas_paths(PROFILE)) == set(SPRITES.canvases)
    assert set(STATUS_BAR.vector_paths(PROFILE)) == set(VECTORS)


def test_a_whole_status_bar_is_read_exactly(reader: StatusBarReader) -> None:
    reading = reader.read(frame(bar()))

    assert reading.status is Status.READ
    assert reading.value == StatusBar(
        level=123,
        hp=1500,
        max_hp=2000,
        mp=300,
        max_mp=450,
        exp=98765,
        exp_percent=12.34,
    )
    assert reading.frame_time == 12.5


def test_hp_zero_is_a_value_not_a_misread(reader: StatusBarReader) -> None:
    reading = reader.read(frame(bar(hp="[0/2000]")))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert reading.value.hp == 0


def test_a_single_digit_level_is_read(reader: StatusBarReader) -> None:
    reading = reader.read(frame(bar(level="7")))

    assert reading.value is not None
    assert reading.value.level == 7


def test_the_bar_is_found_anywhere_and_again_after_a_resize(
    reader: StatusBarReader,
) -> None:
    small = reader.read(frame(bar()))
    searches = reader.locator.searches
    again = reader.read(frame(bar()))
    larger = np.full((150, 520, 3), 40, dtype=np.uint8)
    larger[30:130, 40:480] = bar()
    resized = reader.read(frame(larger))

    assert small.value == again.value == resized.value
    assert reader.locator.searches == searches + 1


# -- ABSENT, COVERED, UNSURE --------------------------------------------------


def test_an_empty_frame_is_absent_when_the_frame_check_passes(
    reader: StatusBarReader, mocker: MockerFixture
) -> None:
    mocker.patch.object(reader._frame_check, "frame_usable", return_value=None)  # pyright: ignore[reportPrivateUsage]
    blank = np.full((100, 440, 3), 40, dtype=np.uint8)

    reading = reader.read(frame(blank))

    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_a_covered_background_is_covered_not_misread(
    reader: StatusBarReader,
) -> None:
    pixels = bar()
    bx, by = POINT[0] - BACKGROUND_ORIGIN[0], POINT[1] - BACKGROUND_ORIGIN[1]
    pixels[by : by + 5, bx + 100 : bx + 140] = 0

    reading = reader.read(frame(pixels))

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert BACKGROUND in reading.detail


def test_a_covered_label_leaves_the_frame_unusable(reader: StatusBarReader) -> None:
    pixels = bar()
    lx, ly = POINT[0] - LABEL_ORIGIN[0], POINT[1] - LABEL_ORIGIN[1]
    pixels[ly : ly + 4, lx : lx + 300] = 0

    reading = reader.read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


def test_a_frame_that_is_not_ok_is_unsure(reader: StatusBarReader) -> None:
    reading = reader.read(frame(bar(), ok=False, reason="window not in front"))

    assert reading.status is Status.UNSURE
    assert "window not in front" in reading.detail


@pytest.mark.parametrize(
    ("kwargs", "named"),
    [
        ({"level": ""}, "level: ''"),
        ({"level": "1234"}, "level: '1234'"),
        ({"hp": "[1500/]"}, "hp: '[1500/]'"),
        ({"hp": "[15//2000]"}, "hp: '[15//2000]'"),
        ({"mp": "300"}, "mp: '300'"),
        ({"exp": "98765"}, "exp: '98765'"),
        ({"exp": "98765[12.%]"}, "exp: '98765[12.%]'"),
    ],
)
def test_a_string_that_does_not_parse_is_unsure_and_says_which(
    reader: StatusBarReader, kwargs: dict[str, str], named: str
) -> None:
    reading = reader.read(frame(bar(**kwargs)))  # pyright: ignore[reportArgumentType]

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert reading.detail == named


def test_numbers_drawn_over_the_bar_do_not_hide_it() -> None:
    """The client draws the numbers over the bar's own sprites, so their pixels
    aren't compared: with an opaque background under them, the bar still reads."""
    closed = dict(SPRITES.canvases)
    solid = noise(340, 36)
    solid[7:11, :, 3] = 0  # where the label is drawn
    closed[BACKGROUND] = Sprite(BACKGROUND, solid, BACKGROUND_ORIGIN)
    sprites = ReaderSprites("test", closed, dict(VECTORS))
    pixels = np.full((100, 440, 3), 40, dtype=np.uint8)
    bx, by = POINT[0] - BACKGROUND_ORIGIN[0], POINT[1] - BACKGROUND_ORIGIN[1]
    paste(pixels, solid, bx, by)
    lx, ly = POINT[0] - LABEL_ORIGIN[0], POINT[1] - LABEL_ORIGIN[1]
    paste(pixels, sprite_of(GAUGE_LABEL).rgba, lx, ly)
    write(pixels, "87", _LEVEL_DIGITS, VECTORS[_LEVEL_AT])
    write(pixels, "[10/20]", _GAUGE_GLYPHS, VECTORS[_HP_AT])
    write(pixels, "[3/4]", _GAUGE_GLYPHS, VECTORS[_MP_AT])
    write(pixels, "5[1.5%]", _GAUGE_GLYPHS, VECTORS[_EXP_AT])

    reading = StatusBarReader(sprites, FrameCheck(sprites)).read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.value == StatusBar(87, 10, 20, 3, 4, 5, 1.5)


def test_exp_grouped_in_thousands_is_read(reader: StatusBarReader) -> None:
    reading = reader.read(frame(bar(exp="2,869[6.08%]")))

    assert reading.value is not None
    assert (reading.value.exp, reading.value.exp_percent) == (2869, 6.08)


def test_what_follows_the_closing_bracket_is_not_read(
    reader: StatusBarReader,
) -> None:
    """The strip runs on to the next number's label, which can match small glyphs."""
    pixels = bar(hp="[1500/2000]")
    x, y = POINT[0] + VECTORS[_HP_AT][0] + 56, POINT[1] + VECTORS[_HP_AT][1]
    paste(pixels, sprite_of(_GAUGE_GLYPHS["5"]).rgba, x, y)

    reading = reader.read(frame(pixels))

    assert reading.value is not None
    assert reading.value.hp == 1500
