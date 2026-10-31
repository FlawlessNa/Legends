"""
The quick slots reader on synthetic frames: a plain background with made-up
labels and digit sprites drawn in a grid, counts under them, and occluders
painted over them. No client pixels.
"""

import numpy as np
import pytest

from botting.screen import Frame, Reading, Status
from game_data.sprites import Sprite
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.quick_slots import (
    DIGITS,
    KEY_NAMES,
    SEARCH_EVERY,
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


def frame(
    pixels: np.ndarray, ok: bool = True, reason: str = "", at: float = 3.0
) -> Frame:
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), at, True, ok, reason)


def settle(
    quick_slots: QuickSlotsReader, pixels: np.ndarray, at: float = 0.0
) -> Reading[QuickSlots]:
    """Read `pixels` twice, `SEARCH_EVERY` apart, which is what it takes for the
    numbering to be trusted. Returns the second reading."""
    quick_slots.read(frame(pixels, at=at))
    return quick_slots.read(frame(pixels, at=at + SEARCH_EVERY))


def settled(pixels: np.ndarray) -> Reading[QuickSlots]:
    return settle(reader(), pixels)


def occlude(pixels: np.ndarray, x: int, y: int, w: int, h: int) -> None:
    pixels[y : y + h, x : x + w] = 200


# Keys used below, with slot numbers (row-major, 4 to a row):
#   1: "1"   2: "2"   3: "3"   4: "4"
#   5: "5"   6: "6"   7: "7"   8: "8"
GRID = {
    "1": (0, 0),
    "2": (0, 1),
    "3": (0, 2),
    "4": (0, 3),
    "5": (1, 0),
    "6": (1, 1),
    "7": (1, 2),
    "8": (1, 3),
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

    reading = settled(pixels)

    assert reading.status is Status.READ
    assert reading.frame_time == SEARCH_EVERY
    slots = slots_of(reading.value)
    assert {k: (s.row, s.column, s.count) for k, s in slots.items()} == {
        "1": (1, 1, 181),
        "2": (1, 2, None),
        "3": (1, 3, None),
        "4": (1, 4, None),
        "5": (2, 1, None),
        "6": (2, 2, 5),
        "7": (2, 3, None),
        "8": (2, 4, None),
    }
    assert (slots["6"].x, slots["6"].y) == label_at(1, 1)


def test_a_slot_with_no_count_drawn_reads_none() -> None:
    pixels = drawn_grid()

    reading = settled(pixels)

    assert reading.status is Status.READ
    assert all(s.count is None for s in slots_of(reading.value).values())


def test_a_count_belongs_to_the_label_above_it_not_the_one_below() -> None:
    # The count sits nearer the next row's label than its own.
    pixels = drawn_grid()
    draw_count(pixels, 42, 0, 1)

    slots = slots_of(settled(pixels).value)

    assert slots["2"].count == 42
    assert slots["6"].count is None


def test_a_cooldown_number_beside_a_label_is_not_a_count() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 30, 1, 0)
    draw_cooldown(pixels, 2, 1, 0)
    draw_cooldown(pixels, 1, 0, 3)

    reading = settled(pixels)

    assert reading.status is Status.READ
    slots = slots_of(reading.value)
    assert slots["5"].count == 30
    assert slots["4"].count is None


def test_fewer_columns_than_the_layout_reads_covered() -> None:
    pixels = screen()
    for row in range(3):
        draw_label(pixels, ("5", "6", "7")[row], row, 3)

    reading = settled(pixels)

    assert reading.status is Status.COVERED
    assert "1 of the layout's 4 columns" in reading.detail


def test_a_label_under_a_cooldown_shade_is_still_that_label() -> None:
    pixels = drawn_grid()
    x, y = label_at(1, 2)
    h = LABELS["7"].rgba.shape[0]
    # The lower half of the label, and of the slot, is shaded: every pixel
    # darker by the same rule.
    lower = pixels[y + h // 2 : y + 2 * h, x - 2 : x + 40].astype(np.float64)
    pixels[y + h // 2 : y + 2 * h, x - 2 : x + 40] = (lower * 0.8 + 10).astype(np.uint8)

    reading = settled(pixels)

    assert reading.status is Status.READ
    assert slots_of(reading.value)["7"].column == 3


def test_a_short_label_matching_inside_a_longer_one_is_dropped() -> None:
    inner = Sprite(
        LABELS["9"].path, LABELS["8"].rgba[:6, :6].copy(), LABELS["8"].origin
    )
    canvases = {s.path: s for s in (*LABELS.values(), *DIGIT_SPRITES.values(), GAUGE)}
    canvases[inner.path] = inner
    built = ReaderSprites("build", canvases)
    pixels = screen()
    for column, key in enumerate(("8", "1", "2", "3")):
        draw_label(pixels, key, 0, column)

    reading = settle(QuickSlotsReader(built, FrameCheck(built)), pixels)

    assert list(slots_of(reading.value)) == ["8", "1", "2", "3"]


# --- slot(n) -------------------------------------------------------------------


def test_slot_n_is_one_based_and_row_major_four_to_a_row() -> None:
    value = settled(drawn_grid()).value
    assert value is not None

    keys = {n: s.key for n in (1, 2, 3, 4, 5, 6, 7, 8) if (s := value.slot(n))}

    assert keys == {n: str(n) for n in range(1, 9)}


def test_slot_n_is_none_when_its_label_was_not_found() -> None:
    value = settled(drawn_grid()).value
    assert value is not None

    assert value.slot(9) is None
    assert value.slot(12) is None


def test_slot_zero_is_refused() -> None:
    value = settled(drawn_grid()).value
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
    assert settle(quick_slots, pixels).status is Status.READ

    x, y = label_at(1, 1)
    occlude(pixels, x, y, 24, 12)
    reading = quick_slots.read(frame(pixels, at=SEARCH_EVERY + 0.5))

    assert reading.status is Status.COVERED
    assert reading.value is None
    assert "6" in reading.detail


def test_it_reads_again_once_the_label_is_uncovered() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    settle(quick_slots, pixels)
    x, y = label_at(1, 1)
    covered = pixels.copy()
    occlude(covered, x, y, 24, 12)
    quick_slots.read(frame(covered, at=SEARCH_EVERY + 0.5))

    reading = quick_slots.read(frame(pixels, at=SEARCH_EVERY + 1.0))

    assert reading.status is Status.READ


def test_the_first_read_is_unsure_until_two_searches_agree() -> None:
    quick_slots = reader()
    pixels = drawn_grid()

    first = quick_slots.read(frame(pixels, at=0.0))
    early = quick_slots.read(frame(pixels, at=SEARCH_EVERY / 2))
    second = quick_slots.read(frame(pixels, at=SEARCH_EVERY))

    assert (first.status, early.status) == (Status.UNSURE, Status.UNSURE)
    assert second.status is Status.READ


def test_a_first_read_partly_covered_is_corrected_when_it_is_uncovered() -> None:
    # Row 0 covered at first: the labels left are row 1's, which would number
    # as row 1 and make `slot(5)` the wrong slot, for good.
    quick_slots = reader()
    pixels = drawn_grid()
    covered = pixels.copy()
    x, y = label_at(0, 0)
    occlude(covered, x - 5, y - 5, 4 * PITCH + 10, 20)
    unsettled = quick_slots.read(frame(covered, at=0.0))
    readings = [
        quick_slots.read(frame(pixels, at=t))
        for t in (1.0, SEARCH_EVERY, 2 * SEARCH_EVERY)
    ]

    assert unsettled.status is Status.UNSURE
    assert [r.status for r in readings] == [Status.UNSURE] * 2 + [Status.READ]
    value = readings[-1].value
    assert value is not None
    slot = value.slot(5)
    assert slot is not None
    assert slot.key == "5"


def test_a_label_that_legitimately_changed_is_found_again() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    settle(quick_slots, pixels)
    rebound = pixels.copy()
    x, y = label_at(1, 1)
    rebound[y : y + 12, x : x + 24] = BACKGROUND
    draw_label(rebound, "9", 1, 1)  # key 6's slot is bound to 9 now

    covered = quick_slots.read(frame(rebound, at=SEARCH_EVERY + 1.0))
    adopted = quick_slots.read(frame(rebound, at=2 * SEARCH_EVERY))

    assert covered.status is Status.COVERED
    assert adopted.status is Status.READ
    assert "6" not in slots_of(adopted.value)
    assert slots_of(adopted.value)["9"].row == 2


def test_a_label_covered_long_after_settling_reads_covered_until_uncovered() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    draw_count(pixels, 25, 1, 1)
    settle(quick_slots, pixels)
    covered = pixels.copy()
    x, y = label_at(1, 1)
    occlude(covered, x, y, 24, 12)

    during = [
        quick_slots.read(frame(covered, at=t)).status for t in (10.0, 13.5, 17.0, 30.0)
    ]
    after = quick_slots.read(frame(pixels, at=31.0))

    assert during == [Status.COVERED] * 4
    assert after.status is Status.READ
    assert after.value is not None
    slot = after.value.slot(6)
    assert slot is not None
    assert (slot.key, slot.count) == ("6", 25)


def test_a_covered_first_column_never_renumbers_the_grid() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    draw_count(pixels, 8, 0, 0)
    settle(quick_slots, pixels)
    covered = pixels.copy()
    x, y = label_at(0, 0)
    occlude(covered, x - 5, y - 5, 30, 2 * PITCH + 10)

    during = [quick_slots.read(frame(covered, at=t)) for t in (10.0, 13.5, 17.0, 30.0)]
    after = quick_slots.read(frame(pixels, at=31.0))

    assert all(r.status is Status.COVERED and r.value is None for r in during)
    assert after.status is Status.READ
    assert after.value is not None
    first = after.value.slot(1)
    second = after.value.slot(2)
    assert first is not None
    assert second is not None
    assert (first.key, first.count, second.key) == ("1", 8, "2")


def test_a_panel_that_moved_is_adopted_once_a_full_grid_is_found() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    settle(quick_slots, pixels)
    moved = screen()
    for key, (row, column) in GRID.items():
        x, y = label_at(row, column)
        paste(moved, LABELS[key], x + 40, y + 20)
    # Every cell of the 2x4 grid is filled, so the move is a complete grid.
    paste(moved, LABELS["8"], *(label_at(1, 3)[0] + 40, label_at(1, 3)[1] + 20))

    adopted = quick_slots.read(frame(moved, at=10.0))

    assert adopted.status is Status.READ
    slot = adopted.value.slot(1) if adopted.value else None
    assert slot is not None
    assert (slot.x, slot.y) == (label_at(0, 0)[0] + 40, label_at(0, 0)[1] + 20)


def test_labels_are_not_searched_for_every_frame() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    settle(quick_slots, pixels)
    searches = quick_slots.searches

    for t in (7.0, 8.0, 9.0):
        quick_slots.read(frame(pixels, at=t))

    assert quick_slots.searches == searches

    x, y = label_at(1, 1)
    occlude(pixels, x, y, 24, 12)
    for t in (10.0, 10.5, 11.0):
        quick_slots.read(frame(pixels, at=t))

    assert quick_slots.searches == searches + 1


def test_labels_are_searched_again_when_the_client_size_changes() -> None:
    quick_slots = reader()
    assert settle(quick_slots, drawn_grid()).status is Status.READ

    bigger = screen(800, 600)
    for column, key in enumerate(("1", "2", "3", "4")):
        draw_label(bigger, key, 2, column)
    reading = settle(quick_slots, bigger, at=10.0)

    assert reading.status is Status.READ
    assert list(slots_of(reading.value)) == ["1", "2", "3", "4"]


def test_a_count_in_a_slot_with_no_label_found_reads_unsure() -> None:
    pixels = screen()
    for key, (row, column) in GRID.items():
        if key != "8":
            draw_label(pixels, key, row, column)
    draw_count(pixels, 9, 1, 3)

    reading = settled(pixels)

    assert reading.status is Status.UNSURE
    assert "row 2, column 4" in reading.detail


def test_two_counts_for_one_slot_read_unsure() -> None:
    pixels = drawn_grid()
    draw_count(pixels, 12, 0, 0)
    x, y = label_at(0, 0)
    paste(pixels, DIGIT_SPRITES["7"], x + 14, y + 16)

    reading = settled(pixels)

    assert reading.status is Status.UNSURE


def test_digits_outside_the_slots_area_are_not_counts() -> None:
    # The same digits are drawn by other windows: only the slots' area is read.
    pixels = drawn_grid()
    draw_count(pixels, 7, 0, 4)
    x, y = label_at(1, 0)
    paste(pixels, DIGIT_SPRITES["3"], x, y + PITCH + 2)

    reading = settled(pixels)

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

    reading = settled(pixels)

    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


def test_a_cell_with_no_label_keeps_the_numbering_unsettled() -> None:
    # A slot unbound, covered or shaded by a cooldown: a fresh reader can't tell.
    pixels = screen()
    for key, (row, column) in GRID.items():
        if key != "6":
            draw_label(pixels, key, row, column)

    reading = settled(pixels)

    assert reading.status is Status.UNSURE
    assert "row 2, column 2" in reading.detail


def test_a_settled_reader_keeps_a_slots_key_while_a_cooldown_shades_it() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    settle(quick_slots, pixels)
    shaded = pixels.copy()
    x, y = label_at(1, 2)
    # The label's lower rows get a shade that is not one constant change.
    noise = RNG.integers(60, 200, (7, 30, 3), dtype=np.uint8)
    shaded[y + 5 : y + 12, x : x + 30] = noise

    reading = quick_slots.read(frame(shaded, at=SEARCH_EVERY + 1.0))

    assert reading.status is Status.READ
    assert slots_of(reading.value)["7"].column == 3


def test_a_label_a_longer_one_would_also_draw_is_not_taken_for_a_slot() -> None:
    # Like `P`, drawn inside `PgUp`: shaded by a cooldown, the longer label
    # would leave exactly this behind, so the cell is a hole.
    inner = Sprite(LABELS["9"].path, LABELS["8"].rgba[:6, :6].copy(), (0, 0))
    canvases = {s.path: s for s in (*LABELS.values(), *DIGIT_SPRITES.values(), GAUGE)}
    canvases[inner.path] = inner
    built = ReaderSprites("build", canvases)
    pixels = screen()
    for key, (row, column) in GRID.items():
        draw_label(pixels, "9" if key == "8" else key, row, column)

    reading = settle(QuickSlotsReader(built, FrameCheck(built)), pixels)

    assert reading.status is Status.UNSURE
    assert "row 2, column 4" in reading.detail


def test_a_grid_first_seen_with_a_menu_over_the_panel_is_read_once_it_closes() -> None:
    quick_slots = reader()
    pixels = drawn_grid()
    draw_count(pixels, 12, 0, 0)
    covered = pixels.copy()
    x, y = label_at(0, 0)
    occlude(covered, x - 5, y - 5, 3 * PITCH, 2 * PITCH + 10)

    during = [quick_slots.read(frame(covered, at=t)).status for t in (0.0, 3.0, 6.0)]
    after = [quick_slots.read(frame(pixels, at=t)) for t in (10.0, 13.0)]

    assert during == [Status.COVERED] * 3
    assert after[0].status is Status.UNSURE
    assert after[1].status is Status.READ
    assert after[1].value is not None
    slot = after[1].value.slot(1)
    assert slot is not None
    assert (slot.key, slot.count) == ("1", 12)
