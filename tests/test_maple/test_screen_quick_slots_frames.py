"""
The quick slots reader on the real MSCW frame set: every `quick_slots` expected
reading of the current tag. Needs the frames (`python scripts/fetch_frames.py`)
and the extracted game data (`python -m game_data extract`); skips without them.

The frames are replayed as a session: per client size, one reader settles on the
first frame without a cooldown, then reads that size's frames in order, because
a slot's key under a cooldown shade is only known from having seen it unshaded:
the settled reader keeps it (that slot `UNSURE`, no count), and the other slots
read. Every size has an unshaded frame to settle on. A fresh reader never reads a
wrong key or count (below): a shaded slot's key is left `None`.
"""

from typing import Any

import pytest

from botting.screen import Frame, Reading, Status
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.quick_slots import (
    QUICK_SLOTS,
    SEARCH_EVERY,
    QuickSlots,
    QuickSlotsReader,
)
from maple.screen.sprites import (
    FRAME_CHECK,
    Profile,
    ReaderSprites,
    StartupRefused,
    load_reader_sprites,
)
from tests.frame_set import Expected, FrameEntry, FrameSet

pytestmark = pytest.mark.frames


@pytest.fixture(scope="module")
def sprites() -> ReaderSprites:
    try:
        return load_reader_sprites(
            [FRAME_CHECK, QUICK_SLOTS], Profile("Hero", "map"), STORE, config=CONFIG
        )
    except StartupRefused as exc:
        pytest.skip(str(exc))


def _frame(frames: FrameSet, entry: FrameEntry, at: float) -> Frame:
    pixels = frames.pixels(entry)
    h, w = pixels.shape[:2]
    return Frame(pixels, (w, h), at, True, True)


def _summary(reading: Reading[QuickSlots]) -> list[dict[str, Any]] | None:
    if reading.value is None:
        return None
    return [
        {"row": s.row, "column": s.column, "key": s.key, "count": s.count}
        for s in reading.value.slots
    ]


def _quick_slots(frames: FrameSet) -> list[FrameEntry]:
    return [e for e in frames.entries if "quick_slots" in e.expect]


def _fresh_reader_is_exact(
    frames: FrameSet, sprites: ReaderSprites, entry: FrameEntry
) -> bool:
    """Whether a reader seeing only this frame reads what is expected of it,
    and reads it (a frame to settle on)."""
    expected = entry.expect["quick_slots"]
    if expected.status is not Status.READ:
        return False
    reader = QuickSlotsReader(sprites, FrameCheck(sprites))
    reader.read(_frame(frames, entry, 0.0))
    got = reader.read(_frame(frames, entry, SEARCH_EVERY))
    return got.status is Status.READ and _summary(got) == expected.value


def _replayed(
    frames: FrameSet, sprites: ReaderSprites
) -> dict[str, Reading[QuickSlots]]:
    """Each frame read as a session: per client size, one reader settles on the
    first frame a fresh reader reads exactly, then reads that size's frames in
    order. A size with no such frame is read by fresh readers."""
    entries = _quick_slots(frames)
    readings: dict[str, Reading[QuickSlots]] = {}
    for size in sorted({e.client_size for e in entries}):
        group = [e for e in entries if e.client_size == size]
        settling = next(
            (e for e in group if _fresh_reader_is_exact(frames, sprites, e)), None
        )
        reader = QuickSlotsReader(sprites, FrameCheck(sprites))
        if settling is not None:
            reader.read(_frame(frames, settling, 0.0))
            reader.read(_frame(frames, settling, SEARCH_EVERY))
        for i, entry in enumerate(group):
            if settling is None:
                reader = QuickSlotsReader(sprites, FrameCheck(sprites))
                reader.read(_frame(frames, entry, 0.0))
                at = SEARCH_EVERY
            else:
                at = SEARCH_EVERY + 0.05 * (i + 1)
            readings[entry.file] = reader.read(_frame(frames, entry, at))
    return readings


@pytest.fixture(scope="module")
def replayed(
    frames: FrameSet, sprites: ReaderSprites
) -> dict[str, Reading[QuickSlots]]:
    return _replayed(frames, sprites)


def _committed_files() -> list[str]:
    from tests import frame_set

    entries = frame_set.load_expected(
        frame_set.TESTS_FRAMES / f"{frame_set.current_tag()}.json"
    )
    return [e.file for e in entries if "quick_slots" in e.expect]


@pytest.mark.parametrize(
    "file", [pytest.param(f, id=f.removesuffix(".png")) for f in _committed_files()]
)
def test_the_quick_slots_reading_is_the_expected_one(
    file: str, frames: FrameSet, replayed: dict[str, Reading[QuickSlots]]
) -> None:
    entry = next(e for e in frames.entries if e.file == file)
    expected = entry.expect["quick_slots"]
    got = replayed[file]

    assert got.status is expected.status
    assert _summary(got) == expected.value


def _wrong(expected: Expected, got: Reading[QuickSlots]) -> str | None:
    """What `got` claims that the expected reading contradicts: a slot's key or
    count read wrong, a bound slot left out, or a slot that isn't there. A key
    left `None`, or an `UNSURE` slot with no count, claims nothing."""
    if got.value is None:
        return None
    if expected.status is not Status.READ:
        return f"read {got.status.name}, expected {expected.status.name}"
    want = {(s["row"], s["column"]): s for s in expected.value}
    have = {(s.row, s.column): s for s in got.value.slots}
    if set(want) != set(have):
        return f"slots at {sorted(have)}, expected at {sorted(want)}"
    for cell, slot in have.items():
        if slot.key is not None and slot.key != want[cell]["key"]:
            return f"key {slot.key} at {cell}, expected {want[cell]['key']}"
        if slot.status is Status.READ and slot.count != want[cell]["count"]:
            return f"count {slot.count} at {cell}, expected {want[cell]['count']}"
        if slot.status is not Status.READ and slot.count is not None:
            return f"count {slot.count} read in an unsure slot at {cell}"
    return None


def test_a_fresh_reader_never_reads_a_wrong_value(
    frames: FrameSet, sprites: ReaderSprites
) -> None:
    # Never a wrong READ: a reader that hasn't seen the slots unshaded reads
    # every slot it can, and leaves a shaded slot's key unknown (`None`, a
    # lone `P` is not `PgUp`) rather than guess it.
    wrong: list[str] = []
    for entry in _quick_slots(frames):
        reader = QuickSlotsReader(sprites, FrameCheck(sprites))
        reader.read(_frame(frames, entry, 0.0))
        got = reader.read(_frame(frames, entry, SEARCH_EVERY))
        why = _wrong(entry.expect["quick_slots"], got)
        if why is not None:
            wrong.append(f"{entry.file}: {why}")
    assert not wrong, chr(10).join(wrong)
