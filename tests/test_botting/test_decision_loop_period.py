"""
The decision loop's throttle is a period (#508): a decision that took part of
it is followed by the rest, not by the whole, so a position read's time no
longer stretches the interval between decisions.
"""

import asyncio
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from botting.core.decision_maker import DecisionMaker


class Clock:
    """A clock only the decisions and the sleeps move."""

    def __init__(self) -> None:
        self.now = 0.0
        self.starts: list[float] = []
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def run_three_decisions(
    mocker: MockerFixture, clock: Clock, throttle: float, took: float
) -> None:
    mocker.patch(
        "botting.core.decision_maker.time", SimpleNamespace(monotonic=clock.monotonic)
    )
    mocker.patch.object(asyncio, "sleep", clock.sleep)

    async def decide() -> None:
        clock.starts.append(clock.now)
        clock.now += took
        if len(clock.starts) == 3:
            raise asyncio.CancelledError

    maker = SimpleNamespace(_throttle=throttle, correlation_id="")
    asyncio.run(DecisionMaker._decision_loop(maker, "loop", decide))  # type: ignore[arg-type]


def test_a_decision_starts_one_throttle_after_the_last_started(
    mocker: MockerFixture,
) -> None:
    clock = Clock()
    run_three_decisions(mocker, clock, throttle=0.1, took=0.03)
    assert clock.starts == pytest.approx([0.0, 0.1, 0.2])


def test_a_decision_longer_than_the_throttle_is_followed_at_once(
    mocker: MockerFixture,
) -> None:
    clock = Clock()
    run_three_decisions(mocker, clock, throttle=0.1, took=0.25)
    assert clock.sleeps == [0.0, 0.0]
    assert clock.starts == pytest.approx([0.0, 0.25, 0.5])
