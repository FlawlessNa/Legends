"""
Buff confirmation (D9, R1) on sequences of synthetic readings: what a cast's
before and after readings make of it, and which casts `CastCheck` asks for again.
"""

import itertools
from collections.abc import Iterator

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading
from maple.decision_makers.mixins import RebuffMixin
from maple.decision_makers.mixins._buffs_mixins import (
    FRESHNESS_MARGINS,
    BuffsReading,
    CastCheck,
    Confirmation,
    FreshnessMargins,
    buff_confirmation,
)
from maple.screen.buffs import BuffState

# Synthetic margins: the real ones wait for frames (`FRESHNESS_MARGINS`).
MARGINS = FreshnessMargins(drop=0.3, nearly_fresh=0.2)
BUFF = "Haste"


def read(state: BuffState | None) -> BuffsReading:
    if state is None:
        return Reading.unsure(0.0, "frame not usable")
    return Reading.read({BUFF: state}, 0.0)


NOT_SHOWN = BuffState(False)
FRESH = BuffState(True, 0.05)
SHADED = BuffState(True, 0.85)
SHOWN = BuffState(True)  # elapsed not built


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (NOT_SHOWN, SHOWN, Confirmation.CONFIRMED),
        (NOT_SHOWN, FRESH, Confirmation.CONFIRMED),
        (SHADED, FRESH, Confirmation.CONFIRMED),
        (NOT_SHOWN, NOT_SHOWN, Confirmation.NOT_CONFIRMED),
        (SHADED, SHADED, Confirmation.NOT_CONFIRMED),
        (SHADED, BuffState(True, 0.7), Confirmation.NOT_CONFIRMED),
        (SHADED, NOT_SHOWN, Confirmation.NOT_CONFIRMED),
        (None, SHOWN, Confirmation.UNSURE),
        (NOT_SHOWN, None, Confirmation.UNSURE),
        (SHOWN, SHOWN, Confirmation.UNSURE),
        (SHADED, SHOWN, Confirmation.UNSURE),
        (FRESH, FRESH, Confirmation.UNSURE),
    ],
    ids=[
        "appeared",
        "appeared fresh",
        "shaded then fresh",
        "still not shown",
        "still shaded",
        "too small a drop",
        "gone",
        "before unreadable",
        "after unreadable",
        "no elapsed",
        "elapsed after missing",
        "recast nearly fresh",
    ],
)
def test_the_rule(
    before: BuffState | None, after: BuffState | None, expected: Confirmation
) -> None:
    assert buff_confirmation(read(before), read(after), BUFF, MARGINS) is expected


def test_a_buff_missing_from_a_reading_is_unsure() -> None:
    other: BuffsReading = Reading.read({"Bless": SHOWN}, 0.0)

    assert buff_confirmation(other, read(SHOWN), BUFF, MARGINS) is Confirmation.UNSURE


def test_until_margins_are_chosen_a_buff_shown_before_and_after_is_unsure() -> None:
    assert FRESHNESS_MARGINS is None
    assert buff_confirmation(read(SHADED), read(FRESH), BUFF) is Confirmation.UNSURE
    assert (
        buff_confirmation(read(NOT_SHOWN), read(SHOWN), BUFF) is Confirmation.CONFIRMED
    )


def _check(*states: BuffState | None) -> tuple[CastCheck, Iterator[BuffsReading]]:
    readings = iter([read(s) for s in states])
    return (
        CastCheck(
            lambda: next(readings),
            [BUFF],
            lambda b, a, buff: buff_confirmation(b, a, buff, MARGINS),
        ),
        readings,
    )


def casts(check: CastCheck, limit: int = 10) -> int:
    """How many casts `ActionWithValidation` sends: one per False."""
    return sum(1 for _ in itertools.takewhile(lambda _: not check(), range(limit)))


def test_the_first_call_reads_before_the_cast_and_always_casts() -> None:
    check, _ = _check(FRESH, FRESH)

    assert check() is False


def test_shaded_then_fresh_is_confirmed() -> None:
    check, _ = _check(SHADED, FRESH)

    assert casts(check) == 1
    assert check.last == {BUFF: Confirmation.CONFIRMED}


def test_shaded_then_still_shaded_is_retried() -> None:
    check, _ = _check(SHADED, SHADED, SHADED, FRESH)

    assert casts(check) == 3
    assert check.last == {BUFF: Confirmation.CONFIRMED}


def test_each_retry_is_judged_against_the_frame_before_it() -> None:
    """After a NOT_CONFIRMED, the frame just read is the next cast's before."""
    check, _ = _check(NOT_SHOWN, NOT_SHOWN, SHOWN)

    assert casts(check) == 2
    assert check.last == {BUFF: Confirmation.CONFIRMED}


def test_unreadable_is_not_retried(caplog: pytest.LogCaptureFixture) -> None:
    check, readings = _check(NOT_SHOWN, None, NOT_SHOWN)

    with caplog.at_level("INFO"):
        assert casts(check) == 1

    assert check.last == {BUFF: Confirmation.UNSURE}
    assert "unconfirmed" in caplog.text
    assert next(readings).value == {BUFF: NOT_SHOWN}  # not read again


def test_one_buff_not_confirmed_retries_them_all() -> None:
    readings = iter(
        [
            Reading.read({"A": NOT_SHOWN, "B": NOT_SHOWN}, 0.0),
            Reading.read({"A": SHOWN, "B": NOT_SHOWN}, 0.0),
            Reading.read({"A": SHOWN, "B": SHOWN}, 0.0),
        ]
    )
    check = CastCheck(lambda: next(readings), ["A", "B"])

    assert casts(check) == 2


class _Rebuff(RebuffMixin):
    def __init__(self, data: BotData) -> None:
        self.data = data


def test_buffs_are_read_from_a_frame_captured_now(mocker: MockerFixture) -> None:
    data = BotData("Bot")
    frames = iter(
        Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), float(t), True, True)
        for t in itertools.count()
    )
    data.create_attribute("current_frame", lambda: next(frames), threshold=60)
    reader = mocker.Mock()
    reader.read.return_value = read(SHOWN)
    data.set_static("buffs_reader", reader)
    first = data.current_frame

    assert _Rebuff(data)._read_buffs([BUFF]) == read(SHOWN)  # pyright: ignore[reportPrivateUsage]

    frame, buffs = reader.read.call_args.args
    assert frame is not first
    assert buffs == [BUFF]
