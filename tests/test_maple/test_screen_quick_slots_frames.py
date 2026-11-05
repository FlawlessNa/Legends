"""
The quick slots reader on the real MSCW frame set: every `quick_slots` expected
reading of the current tag. Needs the frames (`python scripts/fetch_frames.py`)
and the extracted game data (`python -m game_data extract`); skips without them.

The frames are replayed as a session: per client size, one reader settles on the
first frame without a cooldown, then reads that size's frames in order, because
a slot's key under a cooldown shade is only known from having seen it unshaded.
Every size has an unshaded frame to settle on. A fresh reader never reads a wrong
value (below).
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
from tests.frame_set import FrameEntry, FrameSet

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


# Frames whose expected reading the reader cannot meet: the PgUp (`73`) or
# PgDn (`81`) slot is under a cooldown, whose shade and big number
# (`skillCooldownNumber`, drawn blended) hide its label, so a settled reader
# says COVERED rather than keep the key. No cooldown heuristic is used (a wrong
# READ is worse): see the PR #328 maintainer list. Strict, so a frame that
# starts passing is noticed.
CANNOT_MEET = frozenset(
    [
        "f012_1366x768.png",
        "f013_1366x768.png",
        "f014_1366x768.png",
        "f015_1366x768.png",
        "f016_1366x768.png",
        "f017_1366x768.png",
        "f018_1366x768.png",
        "f019_1366x768.png",
        "f020_1366x768.png",
        "f021_1366x768.png",
        "f022_1366x768.png",
        "f023_1366x768.png",
        "f024_1366x768.png",
        "f025_1366x768.png",
        "f026_1366x768.png",
        "f027_1366x768.png",
        "f028_1366x768.png",
        "f029_1366x768.png",
        "f030_1366x768.png",
        "f031_1366x768.png",
        "f032_1366x768.png",
        "f033_1366x768.png",
        "f034_1366x768.png",
        "f035_1366x768.png",
        "f036_1366x768.png",
        "f037_1366x768.png",
        "f038_1366x768.png",
        "f039_1366x768.png",
        "f041_1366x768.png",
        "f042_1366x768.png",
        "f044_800x600.png",
        "f045_800x600.png",
        "f046_800x600.png",
        "f047_800x600.png",
        "f048_800x600.png",
        "f049_800x600.png",
        "f050_800x600.png",
        "f051_800x600.png",
        "f052_800x600.png",
        "h001_1920x1080_pgup_t10s.png",
        "h001_1920x1080_pgup_t12s.png",
        "h001_1920x1080_pgup_t8s.png",
        "j_1024x768_pagedown_1.png",
        "j_1024x768_pagedown_2.png",
        "j_1024x768_pagedown_3.png",
        "j_1024x768_pagedown_4.png",
        "j_1024x768_pageup_1.png",
        "j_1024x768_pageup_2.png",
        "j_1024x768_pageup_3.png",
        "j_1024x768_pageup_4.png",
        "j_1280x720_pagedown_1.png",
        "j_1280x720_pagedown_2.png",
        "j_1280x720_pagedown_3.png",
        "j_1280x720_pagedown_4.png",
        "j_1366x768_pagedown_1.png",
        "j_1366x768_pagedown_2.png",
        "j_1366x768_pagedown_3.png",
        "j_1366x768_pagedown_4.png",
        "j_1366x768_pageup_1.png",
        "j_1366x768_pageup_2.png",
        "j_1366x768_pageup_3.png",
        "j_1366x768_pageup_4.png",
        "j_800x600_pagedown_1.png",
        "j_800x600_pagedown_2.png",
        "j_800x600_pagedown_3.png",
        "j_800x600_pagedown_4.png",
    ]
)


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


def _case(file: str) -> object:
    mark = (
        pytest.mark.xfail(
            strict=True,
            reason="PgUp/PgDn under a cooldown reads COVERED: PR #328 maintainer list",
        )
        if file in CANNOT_MEET
        else ()
    )
    return pytest.param(file, marks=mark, id=file.removesuffix(".png"))


def _committed_files() -> list[str]:
    from tests import frame_set

    entries = frame_set.load_expected(
        frame_set.TESTS_FRAMES / f"{frame_set.current_tag()}.json"
    )
    return [e.file for e in entries if "quick_slots" in e.expect]


@pytest.mark.parametrize("file", [_case(f) for f in _committed_files()])
def test_the_quick_slots_reading_is_the_expected_one(
    file: str, frames: FrameSet, replayed: dict[str, Reading[QuickSlots]]
) -> None:
    entry = next(e for e in frames.entries if e.file == file)
    expected = entry.expect["quick_slots"]
    got = replayed[file]

    assert got.status is expected.status
    assert _summary(got) == expected.value


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
