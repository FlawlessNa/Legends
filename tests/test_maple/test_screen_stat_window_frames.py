"""
The stat window reader on the real MSCW frame set: every expected `stat_window`
reading, no reading on a frame without the window, and no wrong AP when
something is drawn over it. Every frame in the set shows an AP of 0: an AP to
spend hasn't been captured. Needs the glyphs harvested from the frames
(`python -m toolkit.harvest_glyphs`). Run with `pytest -m frames`.
"""

import pytest

from botting.screen import Frame, Status, find_mask_glyphs
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from maple.screen.stat_window import STAT_WINDOW, StatWindow, StatWindowReader
from tests.frame_set import FrameEntry, FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]


@pytest.fixture(scope="module")
def reader() -> StatWindowReader:
    sprites = load_reader_sprites(
        [FRAME_CHECK, STAT_WINDOW],
        Profile(job="Swordsman", game_map="x"),
        STORE,
        config=CONFIG,
    )
    return StatWindowReader(sprites, FrameCheck(sprites))


def _frame(frames: FrameSet, entry: FrameEntry) -> Frame:
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def _value(value: StatWindow | None) -> dict[str, int | None] | None:
    if value is None:
        return None
    return {
        "available_ap": value.available_ap,
        "speed": value.speed,
        "jump": value.jump,
    }


def _read_entry(frames: FrameSet, file: str) -> FrameEntry:
    return next(e for e in frames.entries if e.file == file)


def test_every_expected_stat_window_reading(
    frames: FrameSet, reader: StatWindowReader
) -> None:
    """One reader reads the whole set in order, across every client resize."""
    wrong: list[str] = []
    statuses: set[Status] = set()
    for entry in frames.entries:
        expected = entry.expect.get("stat_window")
        if expected is None:
            continue
        statuses.add(expected.status)
        reading = reader.read(_frame(frames, entry))
        value = _value(reading.value)
        if (reading.status, value) != (expected.status, expected.value):
            wrong.append(
                f"{entry.file}: expected {expected.status.name} {expected.value}, "
                f"got {reading.status.name} {value} {reading.detail}"
            )
    assert statuses == {Status.READ, Status.COVERED}
    assert not wrong, "\n".join(wrong)


def test_a_frame_without_the_window_is_never_read(
    frames: FrameSet, reader: StatWindowReader
) -> None:
    """Every frame with no `stat_window` expectation shows no stat window (each
    was checked by eye): the reader finds none, or can't read the frame."""
    wrong = [
        f"{entry.file}: {reading.status.name} {reading.value} {reading.detail}"
        for entry in frames.entries
        if "stat_window" not in entry.expect
        for reading in (reader.read(_frame(frames, entry)),)
        if reading.status not in (Status.ABSENT, Status.UNSURE)
    ]
    assert not wrong, "\n".join(wrong)


def test_the_sizes_read_include_800x600(frames: FrameSet) -> None:
    sizes = {
        entry.client_size
        for entry in frames.entries
        if (expected := entry.expect.get("stat_window")) is not None
        and expected.status is Status.READ
    }
    assert {(800, 600), (1366, 768), (1920, 1080)} <= sizes


def test_a_block_over_the_window_never_gives_a_wrong_value(
    frames: FrameSet, reader: StatWindowReader
) -> None:
    """A block painted anywhere over Main's lower half and Detail's values, the
    cursor's size, is either read as the same values or isn't `READ`."""
    entry = _read_entry(frames, "f048_800x600.png")
    expected = entry.expect["stat_window"]
    clean = frames.pixels(entry)
    located = reader.main_locator.locate(
        Frame(clean, entry.client_size, 0.0, True, True)
    )
    assert located is not None
    left, top = located.point
    wrong: list[str] = []
    reads = 0
    for dx in range(0, 370, 6):
        for dy in range(150, 285, 6):
            pixels = clean.copy()
            pixels[top + dy : top + dy + 12, left + dx : left + dx + 8] = (40, 90, 200)
            reading = reader.read(Frame(pixels, entry.client_size, 0.0, True, True))
            if reading.status is Status.READ:
                reads += 1
                if _value(reading.value) != expected.value:
                    wrong.append(f"block at +{dx},+{dy}: read {reading.value}")
    assert reads  # blocks away from the numbers and the parts still read
    assert not wrong, "\n".join(wrong[:10])


def test_an_ap_drawn_with_the_buttons_disabled_is_unsure(
    frames: FrameSet, reader: StatWindowReader
) -> None:
    """An AP above 0 in the box while the +1 buttons are still drawn disabled
    (which the client doesn't do) is never read: the stand-in for the AP to
    spend that the frame set lacks."""
    entry = _read_entry(frames, "m_ability_main_only_1920x1080.png")
    pixels = frames.pixels(entry)
    located = reader.main_locator.locate(
        Frame(pixels, entry.client_size, 0.0, True, True)
    )
    assert located is not None
    zero, five = reader.glyphs["0"], reader.glyphs["5"]
    assert zero.shape == five.shape
    # The 0 drawn in the AP box, from `vector:ap` to the Detail button: its ink
    # becomes the paper's colour, and a 5's ink is drawn in its place.
    left, top = located.point[0] + 90, located.point[1] + 258
    region = pixels[top : top + 15, left : left + 32]
    (hit,) = find_mask_glyphs((region == 0).all(axis=2), {"0": zero}, 0.0)
    h, w = zero.shape
    cell = region[hit.y : hit.y + h, hit.x : hit.x + w]
    cell[zero] = cell[~zero][0]
    cell[five] = 0

    reading = reader.read(Frame(pixels, entry.client_size, 0.0, True, True))

    assert reading.status is Status.UNSURE, reading
    assert reading.detail == "AP: 5, but every +1 button is drawn disabled"
