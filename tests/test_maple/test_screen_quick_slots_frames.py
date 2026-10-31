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


# Frames whose expected reading the reader cannot meet: a cooldown shades a
# slot's label in no constant way, so a settled reader says COVERED (1366x768),
# and 800x600 has no unshaded frame to settle on (UNSURE). See the PR body's
# "maintainer list" (PR #328). Strict, so a frame that starts passing is noticed.
CANNOT_MEET = frozenset(
    [
        "f012",
        "f013",
        "f014",
        "f015",
        "f016",
        "f017",
        "f018",
        "f019",
        "f020",
        "f021",
        "f022",
        "f023",
        "f024",
        "f025",
        "f026",
        "f027",
        "f028",
        "f029",
        "f030",
        "f031",
        "f032",
        "f033",
        "f034",
        "f035",
        "f036",
        "f037",
        "f038",
        "f039",
        "f041",
        "f042",
        "f044",
        "f045",
        "f046",
        "f047",
        "f048",
        "f049",
        "f050",
        "f051",
        "f052",
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
            reason="cooldown shade / no unshaded 800x600 frame: PR #328 maintainer list",
        )
        if file[:4] in CANNOT_MEET
        else ()
    )
    return pytest.param(file, marks=mark, id=file[:4])


def _committed_files() -> list[str]:
    from tests import frame_set

    entries = frame_set.load_expected(frame_set.TESTS_FRAMES / "v1.json")
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
