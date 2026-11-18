"""
The on-screen map check at start (#387, epic #302 Part 2 D2).

- **A named map** (`map: <name or id>`): the bot doesn't start when the minimap
  shows another map, read by `MinimapReader.is_expected_map`, the canvas match.
- **`map: auto`**: the map is identified once (`MapIdentifier`), from the
  banner's title confirmed by the canvas match.

Either way, frames are read for up to `WINDOW` seconds, and the first `READ`
decides. Nothing read in that time is a refusal too: an unidentified map is
never guessed (C-NOGUESS). A refusal is a `StartupRefused`, as a missing game
data store is (#307): the Engine fails, and the launcher exits non-zero.

The minimap is shown first, by the caller (`MapleBot`), which may press the
minimap key; nothing here sends input.
"""

import logging
import time
from collections.abc import Callable

from botting import PARENT_LOG
from botting.screen import Reading
from maple.screen.sprites import StartupRefused

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

WINDOW = 3.0
"""How long frames are read for before a map that can't be told refuses the
start, in seconds (#387)."""

INTERVAL = 0.1
"""The pause between two reads, in seconds."""


def first_read[T](
    read: Callable[[], Reading[T]],
    window: float = WINDOW,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Reading[T]:
    """
    `read()` again until it is `READ` or `window` seconds have passed since the
    first: the `READ` reading, or the last one.
    """
    start = clock()
    while True:
        reading = read()
        if reading.value is not None or clock() - start >= window:
            return reading
        sleep(INTERVAL)


def _said[T](reading: Reading[T]) -> str:
    return f"{reading.status.value}: {reading.detail or 'no detail'}"


def check_named_map(
    read: Callable[[], Reading[bool]],
    label: str,
    window: float = WINDOW,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """
    That the minimap shows the profile's map.

    :param read: Whether the minimap in a fresh frame is the map's
        (`is_expected_map`).
    :param label: The map, as messages name it.
    :raises StartupRefused: It shows another map, or that can't be told
        within `window` seconds.
    """
    reading = first_read(read, window, clock=clock, sleep=sleep)
    if reading.value is True:
        logger.info("On-screen map check: the minimap shows %s.", label)
        return
    if reading.value is False:
        message = (
            f"Refusing to start: the minimap shows another map than {label}, "
            f"which the profile names ({reading.detail})."
        )
    else:
        message = (
            f"Refusing to start: the minimap couldn't be checked against {label} "
            f"within {window:g} s (last read {_said(reading)})."
        )
    logger.critical(message)
    raise StartupRefused(message)


def identify_map(
    read: Callable[[], Reading[int]],
    window: float = WINDOW,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Reading[int]:
    """
    The map the minimap shows, for `map: auto`.

    :param read: The map identified in a fresh frame (`MapIdentifier.identify`).
    :returns: The `READ` reading: its value is the map id, its detail how it
        was told.
    :raises StartupRefused: It can't be told within `window` seconds.
    """
    reading = first_read(read, window, clock=clock, sleep=sleep)
    if reading.value is not None:
        return reading
    message = (
        f"Refusing to start: `map: auto` couldn't identify the map within "
        f"{window:g} s (last read {_said(reading)}). Name the map in the "
        "profile's `map`, or show the minimap expanded with its banner."
    )
    logger.critical(message)
    raise StartupRefused(message)
