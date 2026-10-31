"""
The quick slots reader on the real MSCW frame set: every `quick_slots` expected
reading of the current tag. Needs the frames (`python scripts/fetch_frames.py`)
and the extracted game data (`python -m game_data extract`); skips without them.

The frames are replayed as a session: per client size, one reader settles on the
first frame without a cooldown, then reads that size's frames in order, because
a slot's key under a cooldown shade is only known from having seen it unshaded.
A fresh reader never reads a wrong value (below); 800x600 has no unshaded frame
to settle on, so its frames are expected `UNSURE` and only the fresh test runs.
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


def _on_cooldown(entry: FrameEntry) -> bool:
    return "cooldown" in entry.notes


def test_every_expected_quick_slots_reading_is_read(
    frames: FrameSet, sprites: ReaderSprites
) -> None:
    entries = _quick_slots(frames)
    assert entries
    wrong: list[str] = []
    for size in sorted({e.client_size for e in entries}):
        group = [e for e in entries if e.client_size == size]
        settling = next(
            (
                e
                for e in group
                if e.expect["quick_slots"].status is Status.READ and not _on_cooldown(e)
            ),
            None,
        )
        if settling is None:
            # Every frame of this size has a cooldown (v1 at 800x600): no reader
            # has seen the slots unshaded, and `P` (key 25) is drawn inside `PgUp`
            # and `PgDn`, so there is nothing to compare these against yet.
            continue
        reader = QuickSlotsReader(sprites, FrameCheck(sprites))
        reader.read(_frame(frames, settling, 0.0))
        reader.read(_frame(frames, settling, SEARCH_EVERY))
        for i, entry in enumerate(group):
            # Close together, so no search happens: the remembered labels are read.
            got = reader.read(_frame(frames, entry, SEARCH_EVERY + 0.05 * (i + 1)))
            expected: Expected = entry.expect["quick_slots"]
            if got.status is not expected.status or _summary(got) != expected.value:
                wrong.append(
                    f"{entry.file}: expected {expected.status.name}, "
                    f"read {got.status.name} {got.detail}"
                )
    assert not wrong, chr(10).join(wrong)


def test_a_fresh_reader_never_reads_a_wrong_value(
    frames: FrameSet, sprites: ReaderSprites
) -> None:
    # Never a wrong READ: a reader that hasn't seen the slots unshaded reads a
    # frame exactly, or says UNSURE, which it must on every cooldown frame
    # whose slot labels it can't recognise (a lone `P` is not `PgUp`).
    wrong: list[str] = []
    unsure = 0
    for entry in _quick_slots(frames):
        reader = QuickSlotsReader(sprites, FrameCheck(sprites))
        reader.read(_frame(frames, entry, 0.0))
        got = reader.read(_frame(frames, entry, SEARCH_EVERY))
        expected = entry.expect["quick_slots"]
        exact = got.status is expected.status and _summary(got) == expected.value
        if got.status is Status.UNSURE:
            unsure += 1
        elif not exact:
            wrong.append(f"{entry.file}: read {got.status.name} {_summary(got)}")
    assert not wrong, chr(10).join(wrong)
    assert unsure
