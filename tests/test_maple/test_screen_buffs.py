"""
The buffs reader, on synthetic frames: a noise background the test composes,
a slot base and skill icons it draws itself, and occluders it paints. Nothing
here is client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.buffs import (
    BUFFS,
    ICON_BASE,
    BuffsReader,
    BuffState,
)
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.sprites import GAUGE_LABEL, Profile, ReaderSprites

RNG = np.random.default_rng(312)
SIZE = 32
WIDTH, HEIGHT = 400, 300
LIGHT = (136, 170, 204)


def _shape() -> np.ndarray:
    """A 32x32 square with its corners cut, like the client's slot."""
    opaque = np.ones((SIZE, SIZE), bool)
    for y, cut in enumerate((3, 2, 1)):
        for row in (y, SIZE - 1 - y):
            opaque[row, :cut] = False
            opaque[row, SIZE - cut :] = False
    return opaque


SHAPE = _shape()


def _outlined(face: np.ndarray) -> np.ndarray:
    """`face`'s RGB inside the shape, a black outline and a light ring."""
    rgba = np.zeros((SIZE, SIZE, 4), np.uint8)
    rgba[SHAPE, :3] = face[SHAPE]
    rgba[SHAPE, 3] = 255
    padded = np.pad(SHAPE, 1)
    inner = SHAPE & (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    padded = np.pad(inner, 1)
    core = inner & (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    rgba[inner & ~core, :3] = LIGHT
    rgba[SHAPE & ~inner, :3] = 0
    return rgba


def _icon() -> np.ndarray:
    return _outlined(RNG.integers(40, 256, (SIZE, SIZE, 3), dtype=np.uint8))


BASE = _outlined(np.full((SIZE, SIZE, 3), 255, np.uint8))
ICONS = {"Haste": _icon(), "Bless": _icon(), "Other": _icon()}
LABEL = RNG.integers(0, 256, (4, 60, 4), dtype=np.uint8)
LABEL[:, :, 3] = 255


def build_sprites() -> ReaderSprites:
    return ReaderSprites(
        "test",
        {
            GAUGE_LABEL: Sprite(GAUGE_LABEL, LABEL, (0, 0)),
            ICON_BASE: Sprite(ICON_BASE, BASE, (0, 0)),
        },
        {},
        {name: Sprite(name, rgba, (0, SIZE)) for name, rgba in ICONS.items()},
    )


def screen(*shown: str, shade: float = 0.0, countdown: bool = False) -> np.ndarray:
    """
    A frame showing `shown`'s icons packed leftwards from the top-right corner,
    as the client draws them: tinted grey, the bottom `shade` share darkened,
    the countdown's digits over the middle, and the outline drawn exactly.
    """
    pixels = RNG.integers(60, 200, (HEIGHT, WIDTH, 3), dtype=np.uint8)
    paste(pixels, LABEL, 100, HEIGHT - 10)
    for i, name in enumerate(shown):
        draw(pixels, ICONS[name], slot_x(i), 3, shade, countdown)
    return pixels


def slot_x(i: int) -> int:
    return WIDTH - 3 - SIZE * (i + 1)


def draw(
    pixels: np.ndarray,
    rgba: np.ndarray,
    x: int,
    y: int,
    shade: float = 0.0,
    countdown: bool = False,
) -> None:
    face = rgba[:, :, 2::-1].astype(np.float64) * 0.85
    shaded_from = SIZE - round(SIZE * shade)
    face[shaded_from:] *= 0.45
    if countdown:
        face[12:21, 9:22] = (0, 230, 250)
    outline = rgba[:, :, :3].max(axis=2) == 0
    face[outline] = 0
    area = pixels[y : y + SIZE, x : x + SIZE]
    keep = rgba[:, :, 3] == 255
    area[keep] = face.astype(np.uint8)[keep]


def paste(pixels: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    keep = rgba[:, :, 3] == 255
    h, w = rgba.shape[:2]
    pixels[y : y + h, x : x + w][keep] = rgba[:, :, 2::-1][keep]


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 7.5, True, ok, reason)


@pytest.fixture
def reader() -> BuffsReader:
    sprites = build_sprites()
    return BuffsReader(sprites, FrameCheck(sprites))


ASKED = ("Haste", "Bless")


def shown(reader: BuffsReader, pixels: np.ndarray) -> dict[str, bool]:
    reading = reader.read(frame(pixels), ASKED)
    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    return {name: state.shown for name, state in reading.value.items()}


def test_no_slot_reads_every_buff_not_shown(reader: BuffsReader) -> None:
    reading = reader.read(frame(screen()), ASKED)

    assert reading.status is Status.READ
    assert reading.value == {"Haste": BuffState(False), "Bless": BuffState(False)}
    assert reading.frame_time == 7.5


def test_a_shown_buff_is_read_and_its_freshness_isnt_built(
    reader: BuffsReader,
) -> None:
    reading = reader.read(frame(screen("Bless")), ASKED)

    assert reading.value == {
        "Haste": BuffState(False),
        "Bless": BuffState(True, elapsed=None),
    }


def test_two_slots_side_by_side_are_both_read(reader: BuffsReader) -> None:
    assert shown(reader, screen("Haste", "Bless")) == {"Haste": True, "Bless": True}


@pytest.mark.parametrize("shade", [0.5, 1.0])
def test_a_shaded_icon_with_its_countdown_is_still_shown(
    reader: BuffsReader, shade: float
) -> None:
    pixels = screen("Haste", shade=shade, countdown=True)

    assert shown(reader, pixels) == {"Haste": True, "Bless": False}


def test_a_buff_not_asked_for_is_not_taken_for_one(reader: BuffsReader) -> None:
    assert shown(reader, screen("Other")) == {"Haste": False, "Bless": False}


def test_only_the_buffs_asked_for_are_in_the_reading(reader: BuffsReader) -> None:
    reading = reader.read(frame(screen("Haste", "Bless")), ["Bless"])

    assert reading.value == {"Bless": BuffState(True)}


def test_a_black_band_at_the_top_isnt_a_row_of_slots(reader: BuffsReader) -> None:
    pixels = screen()
    pixels[:100] = 0

    assert shown(reader, pixels) == {"Haste": False, "Bless": False}


def test_an_icon_lower_than_the_buff_row_is_not_read(reader: BuffsReader) -> None:
    """A skill icon elsewhere, such as in the quick slots, isn't a buff."""
    pixels = screen()
    draw(pixels, ICONS["Haste"], 200, HEIGHT - 60)

    assert shown(reader, pixels) == {"Haste": False, "Bless": False}


def test_a_hole_in_the_row_is_covered(reader: BuffsReader) -> None:
    pixels = screen("Haste", "Bless", "Other")
    pixels[10:20, slot_x(1) + 10 : slot_x(1) + 20] = 0  # hides nothing exact
    pixels[0:40, slot_x(1) : slot_x(1) + 5] = 250  # over the middle slot's edge

    reading = reader.read(frame(pixels), ASKED)

    assert reading.status is Status.COVERED
    assert reading.value is None


def test_a_slot_on_the_row_drawn_only_in_part_is_covered(
    reader: BuffsReader,
) -> None:
    """A block over the left slot's edge hides its outline, not the row."""
    pixels = screen("Haste", "Bless")
    pixels[0:15, slot_x(1) - 4 : slot_x(1) + 8] = 250

    reading = reader.read(frame(pixels), ASKED)

    assert reading.status is Status.COVERED
    assert "drawn only in part" in reading.detail


def test_a_black_corner_off_the_row_isnt_a_slot_drawn_in_part(
    reader: BuffsReader,
) -> None:
    """A window's black frame shows two sides of an outline: not a slot."""
    pixels = screen("Haste")
    pixels[40, 20:120] = 0
    pixels[40:100, 20] = 0
    pixels[3, 20:120] = 0
    pixels[3:60, 20] = 0

    assert shown(reader, pixels) == {"Haste": True, "Bless": False}


def test_a_covered_first_slot_is_covered_once_the_row_was_seen(
    reader: BuffsReader,
) -> None:
    assert shown(reader, screen("Haste", "Bless")) == {"Haste": True, "Bless": True}
    pixels = screen("Haste", "Bless")
    pixels[0:40, slot_x(0) + 20 : WIDTH] = 250  # a window over the first slot

    reading = reader.read(frame(pixels), ASKED)

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert "first buff slot" in reading.detail


def test_the_row_closing_up_after_a_buff_ends_isnt_covered(
    reader: BuffsReader,
) -> None:
    assert shown(reader, screen("Haste", "Bless"))
    assert shown(reader, screen("Bless")) == {"Haste": False, "Bless": True}


def test_a_new_client_size_forgets_where_the_row_started(
    reader: BuffsReader,
) -> None:
    assert shown(reader, screen("Haste", "Bless"))
    wider = np.concatenate(
        [screen("Haste"), RNG.integers(60, 200, (HEIGHT, 50, 3), dtype=np.uint8)],
        axis=1,
    )

    assert reader.read(frame(wider), ASKED).status is Status.READ


def test_an_unusable_frame_is_unsure(reader: BuffsReader) -> None:
    reading = reader.read(frame(screen("Haste"), ok=False, reason="moved"), ASKED)

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert "moved" in reading.detail


def test_a_frame_without_the_ui_at_1_to_1_is_unsure(reader: BuffsReader) -> None:
    pixels = screen("Haste")
    pixels[HEIGHT - 20 :] = 0

    reading = reader.read(frame(pixels), ASKED)

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


def test_a_buff_whose_icon_wasnt_loaded_is_a_programming_error(
    reader: BuffsReader,
) -> None:
    with pytest.raises(KeyError, match="Meso Up"):
        reader.read(frame(screen()), ["Meso Up"])


def test_the_declaration_names_the_base_and_the_profiles_buffs() -> None:
    profile = Profile(job="Cleric", game_map="x", buffs=("Bless", "Invincible"))

    assert BUFFS.canvas_paths(profile) == (ICON_BASE,)
    assert BUFFS.skill_names(profile) == ("Bless", "Invincible")
