"""
The status bar reader on the real MSCW frame set: every expected `status_bar`
reading, at every client size in the set. Run with `pytest -m frames`.
"""

import dataclasses

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.sprites import Profile, load_reader_sprites
from maple.screen.status_bar import STATUS_BAR, StatusBarReader
from tests.frame_set import FrameSet

pytestmark = [pytest.mark.frames, pytest.mark.client_files]


@pytest.fixture(scope="module")
def reader() -> StatusBarReader:
    sprites = load_reader_sprites(
        [STATUS_BAR], Profile(job="Swordsman", game_map="x"), STORE, config=CONFIG
    )
    return StatusBarReader(sprites, FrameCheck(sprites))


def test_every_expected_status_bar_reading(
    frames: FrameSet, reader: StatusBarReader
) -> None:
    """One reader reads the whole set in order, across every client resize."""
    wrong: list[str] = []
    checked = 0
    for entry in frames.entries:
        expected = entry.expect.get("status_bar")
        if expected is None:
            continue
        checked += 1
        reading = reader.read(
            Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)
        )
        value = dataclasses.asdict(reading.value) if reading.value else None
        if (reading.status, value) != (expected.status, expected.value):
            wrong.append(
                f"{entry.file}: expected {expected.status.name} {expected.value}, "
                f"got {reading.status.name} {value} {reading.detail}"
            )
    assert checked
    assert not wrong, "\n".join(wrong)


def test_the_sizes_in_the_set_are_all_read(frames: FrameSet) -> None:
    sizes = {
        entry.client_size
        for entry in frames.entries
        if entry.expect.get("status_bar") and entry.expect["status_bar"].value
    }
    assert {(800, 600), (1024, 768), (1366, 768), (1920, 1080)} <= sizes


def test_a_cursor_over_the_numbers_never_gives_a_wrong_value(
    frames: FrameSet, reader: StatusBarReader
) -> None:
    """A block painted over any part of the numbers is either read as the same
    values or isn't `READ`: a hidden glyph never becomes a different number."""
    entry = next(
        e
        for e in frames.entries
        if e.client_size == (1366, 768)
        and e.expect.get("status_bar")
        and e.expect["status_bar"].status is Status.READ
    )
    expected = entry.expect["status_bar"]
    clean = frames.pixels(entry)
    located = reader.locator.locate(Frame(clean, entry.client_size, 0.0, True, True))
    assert located is not None
    # The bar's own area: the strips, plus a margin either side.
    left, top = located.point[0] + 40, located.point[1] + 40
    wrong: list[str] = []
    for dx in range(0, 520, 4):
        for dy in (0, 10):
            pixels = clean.copy()
            pixels[top + dy : top + dy + 14, left + dx : left + dx + 12] = (
                200,
                100,
                50,
            )
            reading = reader.read(Frame(pixels, entry.client_size, 0.0, True, True))
            if reading.status is Status.READ:
                value = dataclasses.asdict(reading.value) if reading.value else None
                if value != expected.value:
                    wrong.append(f"block at +{dx},+{dy}: read {value}")
    assert not wrong, "\n".join(wrong[:10])
