"""
The on-screen map check at start: how long it reads, and what refuses the
start. Readings are stubbed and the clock is fake; nothing is on screen.
"""

from collections.abc import Callable, Iterator

import pytest

from botting.screen import Reading
from maple.bots.map_check import (
    INTERVAL,
    WINDOW,
    check_named_map,
    first_read,
    identify_map,
)
from maple.screen.sprites import StartupRefused


class _Clock:
    """A clock that `sleep` moves on, and that each read moves on too."""

    def __init__(self, per_read: float = 0.0) -> None:
        self.now = 0.0
        self.per_read = per_read

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _reads[T](clock: _Clock, *readings: Reading[T]) -> Callable[[], Reading[T]]:
    """Each reading in turn, then the last one again; counts as `clock` time."""
    stream: Iterator[Reading[T]] = iter(readings)
    last: list[Reading[T]] = []

    def read() -> Reading[T]:
        clock.now += clock.per_read
        last[:] = [next(stream, last[0] if last else readings[-1])]
        return last[0]

    return read


UNSURE_B: Reading[bool] = Reading.unsure(0.0, "the minimap is minimised")
UNSURE_I: Reading[int] = Reading.unsure(0.0, "no title; no map's minimap is drawn")


def test_the_first_read_reading_is_taken_at_once() -> None:
    clock = _Clock()
    read = _reads(clock, Reading.read(7, 0.0))

    assert first_read(read, clock=clock, sleep=clock.sleep).value == 7
    assert clock.now == 0.0


def test_reads_go_on_until_one_is_read_within_the_window() -> None:
    clock = _Clock()
    read = _reads(clock, UNSURE_I, UNSURE_I, Reading.read(7, 0.0))

    assert first_read(read, clock=clock, sleep=clock.sleep).value == 7
    assert clock.now == pytest.approx(2 * INTERVAL)


def test_reads_stop_once_the_window_has_passed_and_give_the_last() -> None:
    clock = _Clock(per_read=0.5)
    read = _reads(clock, UNSURE_I)

    reading = first_read(read, clock=clock, sleep=clock.sleep)

    assert reading is UNSURE_I
    assert WINDOW <= clock.now < WINDOW + 0.5 + INTERVAL


def test_a_named_map_on_screen_starts() -> None:
    clock = _Clock()

    check_named_map(
        _reads(clock, Reading.read(True, 0.0)), "map 7", clock=clock, sleep=clock.sleep
    )


def test_a_named_map_unsure_at_first_then_shown_starts() -> None:
    clock = _Clock()
    read = _reads(clock, UNSURE_B, Reading.read(True, 0.0))

    check_named_map(read, "map 7", clock=clock, sleep=clock.sleep)


def test_another_map_on_screen_refuses_at_once_with_a_clear_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = _Clock()
    read = _reads(clock, Reading.read(False, 0.0, "2% of map 7's minimap drawn"))

    with pytest.raises(StartupRefused, match="another map than map 7") as refused:
        check_named_map(read, "map 7", clock=clock, sleep=clock.sleep)

    assert clock.now == 0.0
    assert "2% of map 7's minimap drawn" in str(refused.value)
    assert str(refused.value) in caplog.text


def test_a_named_map_unsure_for_the_whole_window_refuses() -> None:
    clock = _Clock(per_read=0.2)

    with pytest.raises(StartupRefused, match="couldn't be checked") as refused:
        check_named_map(
            _reads(clock, UNSURE_B), "map 7", clock=clock, sleep=clock.sleep
        )

    assert clock.now >= WINDOW
    assert "minimised" in str(refused.value)


def test_auto_gives_the_map_identified() -> None:
    clock = _Clock()
    read = _reads(clock, UNSURE_I, Reading.read(10002000, 0.0, "titled"))

    reading = identify_map(read, clock=clock, sleep=clock.sleep)

    assert reading.value == 10002000


def test_auto_unsure_for_the_whole_window_refuses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clock = _Clock(per_read=0.7)

    with pytest.raises(StartupRefused, match="couldn't identify the map") as refused:
        identify_map(_reads(clock, UNSURE_I), clock=clock, sleep=clock.sleep)

    assert clock.now >= WINDOW
    assert "no map's minimap is drawn" in str(refused.value)
    assert str(refused.value) in caplog.text
