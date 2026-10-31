"""
How long one status bar read takes at 1366x768 with the anchor remembered.

A measurement, not a gate (`lab`): it reads the client's own sprites from the
local store (`client_files`), so it runs where the data is, and reports a
number. The frame is composed here from those sprites, not captured, with the
bar's strings drawn on a cleared strip: the real draw order under the numbers
isn't known offline. See the PR for the number and what it does not show.
"""

import statistics
import sys
import time

import numpy as np
import pytest

from botting.screen import Frame
from game_data.config import CONFIG, STORE
from maple.screen.locator import FrameCheck
from maple.screen.sprites import (
    GAUGE_LABEL,
    Profile,
    ReaderSprites,
    load_reader_sprites,
)
from maple.screen.status_bar import (
    _GAUGE_GLYPHS,
    _LEVEL_DIGITS,
    BACKGROUND,
    STATUS_BAR,
    StatusBarReader,
)

pytestmark = [pytest.mark.lab, pytest.mark.client_files]

SIZE = (1366, 768)
ORIGIN = (40, 640)
REPEATS = 200


def _paste(pixels: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    keep = rgba[:, :, 3] == 255
    h, w = rgba.shape[:2]
    pixels[y : y + h, x : x + w][keep] = rgba[:, :, 2::-1][keep]


def _write(
    pixels: np.ndarray,
    sprites: ReaderSprites,
    text: str,
    paths: dict[str, str],
    at: tuple[int, int],
) -> None:
    x, y = at
    first = sprites.canvas(paths[text[0]]).rgba
    pixels[y : y + first.shape[0], x : x + 40 * first.shape[1]] = 30
    for char in text:
        rgba = sprites.canvas(paths[char]).rgba
        _paste(pixels, rgba, x, y)
        x += rgba.shape[1]


def test_one_read_with_the_anchor_remembered(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sprites = load_reader_sprites(
        [STATUS_BAR], Profile(job="Hero", game_map="x"), STORE, config=CONFIG
    )
    pixels = np.full((SIZE[1], SIZE[0], 3), 30, dtype=np.uint8)
    for path in (BACKGROUND, GAUGE_LABEL):
        sprite = sprites.canvas(path)
        _paste(
            pixels,
            sprite.rgba,
            ORIGIN[0] - sprite.origin[0],
            ORIGIN[1] - sprite.origin[1],
        )

    def at(vector: str) -> tuple[int, int]:
        x, y = sprites.vector(vector)
        return ORIGIN[0] + x, ORIGIN[1] + y

    from maple.screen import status_bar as module

    _write(pixels, sprites, "87", _LEVEL_DIGITS, at(module._LEVEL_AT))  # pyright: ignore[reportPrivateUsage]
    _write(pixels, sprites, "[1500/2000]", _GAUGE_GLYPHS, at(module._HP_AT))  # pyright: ignore[reportPrivateUsage]
    _write(pixels, sprites, "[300/450]", _GAUGE_GLYPHS, at(module._MP_AT))  # pyright: ignore[reportPrivateUsage]
    _write(pixels, sprites, "98765[12.34%]", _GAUGE_GLYPHS, at(module._EXP_AT))  # pyright: ignore[reportPrivateUsage]

    # The label is drawn last: whether the client draws it above or below the
    # numbers isn't known offline, and the frame check needs it whole.
    label = sprites.canvas(GAUGE_LABEL)
    _paste(pixels, label.rgba, ORIGIN[0] - label.origin[0], ORIGIN[1] - label.origin[1])

    reader = StatusBarReader(sprites, FrameCheck(sprites))
    first = reader.read(Frame(pixels, SIZE, 0.0, True, True))
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
            f"\nstatus bar read at {SIZE[0]}x{SIZE[1]} (status {first.status.name}): "
            f"median {statistics.median(times):.1f} ms, max {max(times):.1f} ms "
            f"over {REPEATS} reads (target < 15 ms)\n"
        )
