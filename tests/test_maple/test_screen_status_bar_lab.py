"""
How long one status bar read takes at 1366x768 with the anchor remembered.

A measurement, not a gate (`lab`): it reads a real 1366x768 frame of the frame
set and the client's own sprites from the local store, and reports a number.
"""

import statistics
import sys
import time

import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.sprites import Profile, load_reader_sprites
from maple.screen.status_bar import STATUS_BAR, StatusBarReader
from tests.frame_set import FrameSet

pytestmark = [pytest.mark.lab, pytest.mark.frames, pytest.mark.client_files]

SIZE = (1366, 768)
REPEATS = 200


def test_one_read_with_the_anchor_remembered(
    frames: FrameSet, capsys: pytest.CaptureFixture[str]
) -> None:
    sprites = load_reader_sprites(
        [STATUS_BAR], Profile(job="Swordsman", game_map="x"), STORE, config=CONFIG
    )
    entry = next(
        e
        for e in frames.entries
        if e.client_size == SIZE
        and e.expect.get("status_bar")
        and e.expect["status_bar"].status is Status.READ
    )
    pixels = frames.pixels(entry)
    reader = StatusBarReader(sprites, FrameCheck(sprites))
    first = reader.read(Frame(pixels, SIZE, 0.0, True, True))
    assert first.status is Status.READ
    searches = reader.locator.searches

    times: list[float] = []
    for _ in range(REPEATS):
        frame = Frame(pixels, SIZE, 0.0, True, True)
        started = time.perf_counter()
        reader.read(frame)
        times.append((time.perf_counter() - started) * 1000)

    assert reader.locator.searches == searches
    with capsys.disabled():
        sys.stdout.write(
            f"\nstatus bar read at {SIZE[0]}x{SIZE[1]}, {entry.file}: "
            f"median {statistics.median(times):.1f} ms, max {max(times):.1f} ms "
            f"over {REPEATS} reads (target < 15 ms)\n"
        )
