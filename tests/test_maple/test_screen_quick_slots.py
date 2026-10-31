"""
The quick slots reader on synthetic frames: a plain background with made-up
labels and digit sprites drawn in a grid, counts under them, and occluders
painted over them. No client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.quick_slots import (
    DIGITS,
    KEY_NAMES,
    QuickSlots,
    QuickSlotsReader,
    Slot,
)
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

RNG = np.random.default_rng(310)
PITCH = 34
ORIGIN = (200, 150)
BACKGROUND = 40


def sprite(path: str, w: int, h: int) -> Sprite:
    rgba = RNG.integers(0, 256, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, (0, 0))


LABELS = {
    name: sprite(f"UI/QuickSlot.img/key/{name}", int(RNG.integers(10, 24)), 12)
    for name in KEY_NAMES
}
DIGIT_SPRITES = {
    d: sprite(f"UI/Basic.img/ItemNo/{d}", 5 if d == "1" else 8, 11) for d in DIGITS
}
GAUGE = sprite(GAUGE_LABEL, 20, 8)


def sprites() -> ReaderSprites:
    canvases = {s.path: s for s in (*LABELS.values(), *DIGIT_SPRITES.values(), GAUGE)}
    return ReaderSprites("build", canvases)


def reader() -> QuickSlotsReader:
    s = sprites()
    return QuickSlotsReader(s, FrameCheck(s))


def paste(pixels: np.ndarray, s: Sprite, x: int, y: int) -> None:
    h, w = s.rgba.shape[:2]
    pixels[y : y + h, x : x + w] = s.rgba[:, :, 2::-1]


def screen(w: int = 640, h: int = 480) -> np.ndarray:
    pixels = np.full((h, w, 3), BACKGROUND, dtype=np.uint8)
    paste(pixels, GAUGE, 10, h - 12)
    return pixels


def label_at(row: int, column: int) -> tuple[int, int]:
    return ORIGIN[0] + column * PITCH, ORIGIN[1] + row * PITCH


def draw_label(pixels: np.ndarray, key: str, row: int, column: int) -> None:
    paste(pixels, LABELS[key], *label_at(row, column))


def draw_count(pixels: np.ndarray, count: int, row: int, column: int) -> None:
    """The count's digits side by side, starting left of and under the label."""
    x, y = label_at(row, column)
    x, y = x - 3, y + 16
    for char in str(count):
        paste(pixels, DIGIT_SPRITES[char], x, y)
        x += DIGIT_SPRITES[char].rgba.shape[1]


def draw_cooldown(pixels: np.ndarray, number: int, row: int, column: int) -> None:
    """A cooldown number, with the same digits, at the slot's top right."""
    x, y = label_at(row, column)
    paste(pixels, DIGIT_SPRITES[str(number)], x + 24, y)


def frame(pixels: np.ndarray, ok: bool = True, reason: str = "") -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), 3.0, True, ok, reason)


def occlude(pixels: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    pixels[y : y + h, x : x + w] = 200


# Keys used below, with slot numbers (row-major, 4 to a row):
#   1: "1"   2: "2"   3: "3"   4: "4"
#   5: "5"   6: "6"   7: "7"
GRID = {
    "1": (0, 0),
    "2": (0, 1),
    "3": (0, 2),
    "4": (0, 3),
    "5": (1, 0),
    "6": (1, 1),
    "7": (1, 2),
}


def drawn_grid() -> np.ndarray:
    pixels = screen()
    for key, (row, column) in GRID.items():
        draw_label(pixels, key, row, column)
    return pixels


def slots_of(reading_value: QuickSlots | None) -> dict[str, Slot]:
    assert reading_value is not None
    return {s.key: s for s in reading_value.slots}


# --- READ --------------------------------------------------------------------


def test_every_label_found_gives_its_grid_position_key_and_count() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 181, 0, 0)
    draw_count(pixels, 5, 1, 1)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert reading.frame_time == 3.0
    slots = slots_of(reading.value)
    assert {k: (s.row, s.column, s.count) for k, s in slots.items()} == {
        "1": (1, 1, 181),
        "2": (1, 2, None),
        "3": (1, 3, None),
        "4": (1, 4, None),
        "5": (2, 1, None),
        "6": (2, 2, 5),
        "7": (2, 3, None),
    }
    assert (slots["6"].x, slots["6"].y) == label_at(1, 1)


def test_a_slot_with_no_count_drawn_reads_none() -> None:
    pixels = drawn_grid()

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert all(s.count is None for s in slots_of(reading.value).values())


def test_a_count_belongs_to_the_label_above_it_not_the_one_below() -> None:
    # The count sits nearer the next row's label than its own.
    pixels = drawn_grid()
    draw_count(pixels, 42, 0, 1)

    slots = slots_of(reader().read(frame(pixels)).value)

    assert slots["2"].count == 42
    assert slots["6"].count is None


def test_a_cooldown_number_beside_a_label_is_not_a_count() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 30, 1, 0)
    draw_cooldown(pixels, 2, 1, 0)
    draw_cooldown(pixels, 1, 0, 3)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    slots = slots_of(reading.value)
    assert slots["5"].count == 30
    assert slots["4"].count is None


def test_a_short_label_matching_inside_a_longer_one_is_dropped() -> None:
    inner = Sprite(
        LABELS["9"].path, LABELS["8"].rgba[:6, :6].copy(), LABELS["8"].origin
    )
    canvases = {s.path: s for s in (*LABELS.values(), *DIGIT_SPRITES.values(), GAUGE)}
    canvases[inner.path] = inner
    built = ReaderSprites("build", canvases)
    pixels = screen()
    draw_label(pixels, "8", 0, 0)

    reading = QuickSlotsReader(built, FrameCheck(built)).read(frame(pixels))

    assert list(slots_of(reading.value)) == ["8"]


# --- slot(n) -------------------------------------------------------------------


def test_slot_n_is_one_based_and_row_major_four_to_a_row() -> None:
    value = reader().read(frame(drawn_grid())).value
    assert value is not None

    keys = {n: s.key for n in (1, 2, 3, 4, 5, 6, 7) if (s := value.slot(n))}

    assert keys == {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7"}


def test_slot_n_is_none_when_its_label_was_not_found() -> None:
    value = reader().read(frame(drawn_grid())).value
    assert value is not None

    assert value.slot(8) is None
    assert value.slot(12) is None


def test_slot_zero_is_refused() -> None:
    value = reader().read(frame(drawn_grid())).value
    assert value is not None

    with pytest.raises(ValueError, match="from 1"):
        value.slot(0)


# --- ABSENT, COVERED, UNSURE --------------------------------------------------


def test_no_labels_reads_absent_with_no_value() -> None:
    reading = reader().read(frame(screen()))

    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_a_label_found_earlier_that_no_longer_matches_reads_covered() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    assert quick_slots.read(frame(pixels)).status is Status.READ

    x, y = label_at(1, 1)
    occlude(pixels, x, y, 6, 12)
    reading = quick_slots.read(frame(pixels))

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert "6" in reading.detail


def test_it_reads_again_once_the_label_is_uncovered() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    quick_slots.read(frame(pixels))
    x, y = label_at(1, 1)
    covered = pixels.copy()
    occlude(covered, x, y, 6, 12)
    quick_slots.read(frame(covered))

    assert quick_slots.read(frame(pixels)).status is Status.READ


def test_labels_are_searched_again_when_the_client_size_changes() -> None:
    quick_slots = reader()
    assert quick_slots.read(frame(drawn_grid())).status is Status.READ

    bigger = screen(800, 600)
    draw_label(bigger, "1", 2, 2)
    reading = quick_slots.read(frame(bigger))

    assert reading.status is Status.READ
    assert list(slots_of(reading.value)) == ["1"]


def test_a_count_in_a_slot_with_no_label_found_reads_unsure() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 9, 1, 3)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.UNSURE


def test_two_counts_for_one_slot_read_unsure() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 12, 0, 0)
    x, y = label_at(0, 0)
    paste(pixels, DIGIT_SPRITES["7"], x + 14, y + 16)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.UNSURE


def test_digits_outside_the_slots_area_are_not_counts() -> None:
    # The same digits are drawn by other windows: only the slots' area is read.
    pixels = drawn_grid()
    draw_count(pixels, 7, 0, 4)
    x, y = label_at(1, 0)
    paste(pixels, DIGIT_SPRITES["3"], x, y + PITCH + 2)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.READ
    assert all(s.count is None for s in slots_of(reading.value).values())


def test_a_frame_that_is_not_usable_reads_unsure() -> None:
    pixels = drawn_grid()

    reading = reader().read(frame(pixels, ok=False, reason="window not in front"))

    assert reading.status is Status.UNSURE
    assert "window not in front" in reading.detail


def test_a_frame_without_the_ui_at_one_to_one_reads_unsure() -> None:
    pixels = np.full((480, 640, 3), BACKGROUND, dtype=np.uint8)
    draw_label(pixels, "1", 0, 0)

    reading = reader().read(frame(pixels))

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND
