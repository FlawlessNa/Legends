"""
`HeldReading`: what a consumer with no policy for a misread does. It reads the
status first, keeps its previous value unless the reading is `READ`, and logs
the status at debug level, once per change.
"""

import logging
from collections.abc import Callable

import pytest

from botting.screen import Reading
from maple.decision_makers.mixins import HeldReading

LOGGER = "botting.maple.decision_makers.mixins._readings"


def _tenfold(value: int) -> int:
    return value * 10


def _held(absent: Callable[[], int] | None = None) -> HeldReading[int, int]:
    return HeldReading("Owner", "thing", _tenfold, -1, absent=absent)


def test_a_read_sets_the_value_and_a_misread_keeps_it() -> None:
    held = _held()

    assert held(Reading.unsure(0.0, "x")) == -1
    assert held(Reading.read(4, 1.0)) == 40
    assert held(Reading.covered(2.0, "cursor")) == 40
    assert held(Reading.unsure(3.0, "frame")) == 40
    assert held(Reading.absent(4.0)) == 40
    assert held(Reading.read(5, 5.0)) == 50


def test_absent_sets_its_own_value_only_when_given_one() -> None:
    held = _held(absent=lambda: 0)

    held(Reading.read(4, 1.0))

    assert held(Reading.covered(2.0)) == 40
    assert held(Reading.absent(3.0)) == 0


def test_the_status_is_logged_at_debug_once_per_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    held = _held()
    caplog.set_level(logging.DEBUG, logger=LOGGER)

    for reading in (
        Reading.covered(0.0, "cursor"),
        Reading.covered(1.0, "cursor"),
        Reading.read(1, 2.0),
        Reading.read(2, 3.0),
        Reading.covered(4.0, "window"),
    ):
        held(reading)

    logged = [r for r in caplog.records if r.name == LOGGER]
    assert [r.levelno for r in logged] == [logging.DEBUG] * 3
    assert [r.getMessage() for r in logged] == [
        "Owner: thing covered (cursor)",
        "Owner: thing read (no detail)",
        "Owner: thing covered (window)",
    ]
