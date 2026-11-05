"""
The stat window reader, on synthetic frames: panels and buttons of random noise,
made-up glyphs, and occluders the test paints. Nothing here is client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.font import STAT_WINDOW_GLYPHS, GlyphSet
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.sprites import FRAME_CHECK, GAUGE_LABEL, Profile, ReaderSprites
from maple.screen.stat_window import (
    _AP_AT,
    _ATTACK_AT,
    _CLOSE,
    _DETAIL_BUTTON,
    _HIDE,
    _JUMP_AT,
    _NAME_AT,
    _SPEED_AT,
    DETAIL_BACKGROUND,
    DETAIL_UNDER_MAIN,
    MAIN_BACKGROUND,
    STAT_WINDOW,
    STATS,
    StatWindowReader,
    _up_button,
)

PROFILE = Profile(job="Hero", game_map="Anywhere")
RNG = np.random.default_rng(314)
PAPER = (225, 223, 213)
"""The colour the numbers are drawn on, in RGB, as the client's value boxes."""


def noise(w: int, h: int) -> np.ndarray:
    rgba = RNG.integers(1, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return rgba


# Main: 100 x 130, its values right of x=30 from y=20, the AP box from (50, 100).
MAIN_W, MAIN_H = 100, 130
# Detail: 90 x 110, its values right of x=40 from y=10, speed and jump rows below.
DETAIL_W, DETAIL_H = 90, 110
VECTORS = {
    _NAME_AT: (30, 20),
    _AP_AT: (50, 100),
    _ATTACK_AT: (40, 10),
    _SPEED_AT: (40, 60),
    _JUMP_AT: (40, 75),
}
UP_ORIGINS = {stat: (-75, -(25 + 12 * i)) for i, stat in enumerate(STATS)}
STATES = ("disabled", "normal", "mouseOver")


def _main() -> np.ndarray:
    rgba = noise(MAIN_W, MAIN_H)
    rgba[100:130, 50:80, :3] = PAPER  # the AP box
    return rgba


def _detail() -> np.ndarray:
    rgba = noise(DETAIL_W, DETAIL_H)
    rgba[10:90, 40:90, :3] = PAPER  # the values
    return rgba


def _glyph(w: int) -> np.ndarray:
    while True:
        mask = RNG.random((7, w)) < 0.5
        if mask[:, 0].any() and mask[:, -1].any() and mask[0].any() and mask[-1].any():
            return mask


GLYPHS = {**{str(n): _glyph(5) for n in range(10)}, "%": _glyph(7)}


def build_sprites() -> ReaderSprites:
    canvases: dict[str, Sprite] = {
        GAUGE_LABEL: Sprite(GAUGE_LABEL, noise(40, 6), (0, 0)),
        MAIN_BACKGROUND: Sprite(MAIN_BACKGROUND, _main(), (0, 0)),
        DETAIL_BACKGROUND: Sprite(DETAIL_BACKGROUND, _detail(), (0, 0)),
        _CLOSE: Sprite(_CLOSE, noise(8, 8), (-88, -3)),
        _DETAIL_BUTTON: Sprite(_DETAIL_BUTTON, noise(15, 10), (-82, -102)),
        _HIDE: Sprite(_HIDE, noise(8, 8), (-78, -96)),
    }
    for stat, origin in UP_ORIGINS.items():
        for state in STATES:
            path = _up_button(stat, state)
            canvases[path] = Sprite(path, noise(8, 8), origin)
    glyphs = GlyphSet(STAT_WINDOW_GLYPHS, GLYPHS)
    return ReaderSprites(
        "test", canvases, dict(VECTORS), glyph_sets={STAT_WINDOW_GLYPHS.name: glyphs}
    )


SPRITES = build_sprites()
MAIN_AT = (60, 40)
DETAIL_AT = (MAIN_AT[0] + MAIN_W - DETAIL_UNDER_MAIN, MAIN_AT[1] + 30)


def paste(pixels: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    keep = rgba[:, :, 3] == 255
    h, w = rgba.shape[:2]
    area = pixels[y : y + h, x : x + w]
    area[keep] = rgba[:, :, 2::-1][keep]


def paste_sprite(pixels: np.ndarray, path: str, point: tuple[int, int]) -> None:
    sprite = SPRITES.canvas(path)
    paste(pixels, sprite.rgba, point[0] - sprite.origin[0], point[1] - sprite.origin[1])


def write(pixels: np.ndarray, text: str, x: int, y: int) -> None:
    """`text` in black, from the strip's top-left plus a margin, a column apart."""
    x, y = x + 1, y + 3
    for char in text:
        mask = GLYPHS[char]
        h, w = mask.shape
        pixels[y : y + h, x : x + w][mask] = 0
        x += w + 2


def window(
    ap: str = "5",
    speed: str | None = "120%",
    jump: str = "110%",
    buttons: str = "normal",
    size: tuple[int, int] = (360, 240),
) -> np.ndarray:
    """A frame: the status bar's label, then Detail when `speed` isn't `None`,
    then Main over it, with each +1 button in the `buttons` state."""
    pixels = RNG.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
    paste_sprite(pixels, GAUGE_LABEL, (5, size[1] - 10))
    if speed is not None:
        paste_sprite(pixels, DETAIL_BACKGROUND, DETAIL_AT)
        paste_sprite(pixels, _HIDE, DETAIL_AT)
        x, y = VECTORS[_SPEED_AT]
        write(pixels, speed, DETAIL_AT[0] + x, DETAIL_AT[1] + y)
        x, y = VECTORS[_JUMP_AT]
        write(pixels, jump, DETAIL_AT[0] + x, DETAIL_AT[1] + y)
    paste_sprite(pixels, MAIN_BACKGROUND, MAIN_AT)
    paste_sprite(pixels, _CLOSE, MAIN_AT)
    paste_sprite(pixels, _DETAIL_BUTTON, MAIN_AT)
    for stat in STATS:
        paste_sprite(pixels, _up_button(stat, buttons), MAIN_AT)
    x, y = VECTORS[_AP_AT]
    write(pixels, ap, MAIN_AT[0] + x, MAIN_AT[1] + y)
    return pixels


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 7.5, True, ok, reason)


@pytest.fixture
def reader() -> StatWindowReader:
    return StatWindowReader(SPRITES, FrameCheck(SPRITES))


def test_the_declaration_names_every_sprite_the_reader_asks_for() -> None:
    declared = set(STAT_WINDOW.canvas_paths(PROFILE)) | set(
        FRAME_CHECK.canvas_paths(PROFILE)
    )
    assert declared == set(SPRITES.canvases)
    assert set(STAT_WINDOW.vector_paths(PROFILE)) == set(VECTORS)
    assert STAT_WINDOW.glyph_sets == (STAT_WINDOW_GLYPHS.name,)


def test_ap_speed_and_jump_are_read(reader: StatWindowReader) -> None:
    reading = reader.read(frame(window(ap="17", speed="120%", jump="109%")))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert (reading.value.available_ap, reading.value.speed, reading.value.jump) == (
        17,
        120,
        109,
    )
    assert reading.frame_time == 7.5


def test_each_up_button_is_given_by_its_centre_in_client_pixels(
    reader: StatWindowReader,
) -> None:
    reading = reader.read(frame(window()))

    assert reading.value is not None
    for stat, (ox, oy) in UP_ORIGINS.items():
        assert reading.value.up_buttons[stat] == (
            MAIN_AT[0] - ox + 4,
            MAIN_AT[1] - oy + 4,
        )


def test_with_detail_hidden_speed_and_jump_are_none(reader: StatWindowReader) -> None:
    reading = reader.read(frame(window(ap="3", speed=None)))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert (reading.value.available_ap, reading.value.speed, reading.value.jump) == (
        3,
        None,
        None,
    )


def test_an_ap_of_zero_with_the_buttons_disabled_is_read(
    reader: StatWindowReader,
) -> None:
    reading = reader.read(frame(window(ap="0", buttons="disabled")))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert reading.value.available_ap == 0


@pytest.mark.parametrize(
    ("ap", "buttons", "detail"),
    [
        ("0", "normal", "AP: 0, but a +1 button is drawn enabled"),
        ("0", "mouseOver", "AP: 0, but a +1 button is drawn enabled"),
        ("4", "disabled", "AP: 4, but every +1 button is drawn disabled"),
    ],
)
def test_an_ap_the_buttons_disagree_with_is_unsure(
    reader: StatWindowReader, ap: str, buttons: str, detail: str
) -> None:
    reading = reader.read(frame(window(ap=ap, buttons=buttons)))

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert reading.detail == detail


def test_one_enabled_button_is_enough_for_an_ap_above_zero(
    reader: StatWindowReader,
) -> None:
    """A stat at its maximum keeps its button disabled while AP is left."""
    pixels = window(ap="2", buttons="disabled")
    paste_sprite(pixels, _up_button("LUK", "normal"), MAIN_AT)

    reading = reader.read(frame(pixels))

    assert reading.status is Status.READ, reading.detail


def test_no_window_is_absent(reader: StatWindowReader) -> None:
    pixels = RNG.integers(0, 256, (240, 360, 3), dtype=np.uint8)
    paste_sprite(pixels, GAUGE_LABEL, (5, 230))

    reading = reader.read(frame(pixels))

    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_an_unusable_frame_is_unsure(reader: StatWindowReader) -> None:
    reading = reader.read(frame(window(), ok=False, reason="window not in front"))

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert "window not in front" in reading.detail


def test_a_frame_without_the_status_bar_at_1_to_1_is_unsure(
    reader: StatWindowReader,
) -> None:
    pixels = window()
    pixels[-12:, :60] = 30

    reading = reader.read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


@pytest.mark.parametrize(
    ("where", "missing"),
    [
        ((MAIN_AT[0] + 5, MAIN_AT[1] + 50), "Main/backgrnd (labels)"),
        ((MAIN_AT[0] + 40, MAIN_AT[1] + 5), "Main/backgrnd (title bar)"),
        ((MAIN_AT[0] + 20, MAIN_AT[1] + 110), "Main/backgrnd (AP label)"),
        ((DETAIL_AT[0] + 20, DETAIL_AT[1] + 40), "Detail/backgrnd (labels)"),
        ((DETAIL_AT[0] + 50, DETAIL_AT[1] + 2), "Detail/backgrnd (top)"),
    ],
)
def test_an_occluder_over_a_panel_is_covered(
    reader: StatWindowReader, where: tuple[int, int], missing: str
) -> None:
    pixels = window()
    x, y = where
    pixels[y : y + 6, x : x + 6] = (40, 90, 200)

    reading = reader.read(frame(pixels))

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert missing in reading.detail


def test_an_occluder_over_the_ap_is_covered(reader: StatWindowReader) -> None:
    pixels = window(ap="58")
    x, y = VECTORS[_AP_AT]
    pixels[MAIN_AT[1] + y + 4, MAIN_AT[0] + x + 8] = (255, 255, 255)

    reading = reader.read(frame(pixels))

    assert reading.status is Status.COVERED
    assert reading.detail == "AP: 1 pixel(s) over it"


def test_ink_no_glyph_explains_is_unsure(reader: StatWindowReader) -> None:
    pixels = window(ap="6")
    x, y = VECTORS[_AP_AT]
    pixels[MAIN_AT[1] + y + 5, MAIN_AT[0] + x + 20] = 0

    reading = reader.read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert reading.detail == "AP: '6' and ink no glyph explains"


@pytest.mark.parametrize(
    ("ap", "speed", "detail"),
    [
        ("", "120%", "AP: ''"),
        ("05", "120%", "AP: '05'"),
        ("1234", "120%", "AP: '1234'"),
        ("5", "120", "speed: '120'"),
        ("5", "%", "speed: '%'"),
        ("5", "1%20", "speed: '1%20'"),
    ],
)
def test_a_string_that_doesnt_parse_is_unsure(
    reader: StatWindowReader, ap: str, speed: str, detail: str
) -> None:
    reading = reader.read(frame(window(ap=ap, speed=speed)))

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert reading.detail == detail


def test_a_block_anywhere_never_gives_a_wrong_value(reader: StatWindowReader) -> None:
    """A block the cursor's size, anywhere over the window, is either read as
    what is drawn or isn't `READ`."""
    clean = window(ap="47", speed="133%", jump="118%")
    wrong: list[str] = []
    for x in range(MAIN_AT[0] - 4, DETAIL_AT[0] + DETAIL_W, 4):
        for y in range(MAIN_AT[1] - 4, DETAIL_AT[1] + DETAIL_H, 4):
            pixels = clean.copy()
            pixels[y : y + 9, x : x + 6] = (250, 250, 250)
            reading = reader.read(frame(pixels))
            if reading.value is not None and (
                reading.value.available_ap,
                reading.value.speed,
                reading.value.jump,
            ) != (47, 133, 118):
                wrong.append(f"block at {x},{y}: {reading.value}")
    assert not wrong, "\n".join(wrong[:10])


def test_the_same_reader_reads_a_moved_window_and_another_size(
    reader: StatWindowReader,
) -> None:
    assert reader.read(frame(window(ap="9"))).status is Status.READ
    searches = reader.main_locator.searches
    assert reader.read(frame(window(ap="9"))).status is Status.READ
    assert reader.main_locator.searches == searches

    bigger = window(ap="8", size=(420, 300))
    reading = reader.read(frame(bigger))

    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    assert reading.value.available_ap == 8
    assert reader.main_locator.searches == searches + 1
