"""
When `AbilityPointDistributor` opens the AP menu: on a level read higher or
different from the last level read. An unreadable level is not a level-up and
doesn't replace the last level read. Stubbed `status_bar` readings, no client.
"""

import asyncio
import logging
from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from botting.screen import Reading
from maple.decision_makers import ability_point_distributor as module
from maple.decision_makers.ability_point_distributor import AbilityPointDistributor
from maple.screen.status_bar import StatusBar


def read(level: int) -> Reading[StatusBar]:
    return Reading.read(StatusBar(level, 1, 1, 1, 1, 1, 0.0), 1.0)


def unsure() -> Reading[StatusBar]:
    return Reading.unsure(1.0, "hp: ''")


class Harness:
    def __init__(
        self, mocker: MockerFixture, readings: list[Reading[StatusBar]]
    ) -> None:
        self.readings = iter(readings)
        self.data = mocker.Mock()
        self.data.update_attributes.side_effect = self._advance
        self.data.available_ap = 5
        self.menu_opened = mocker.patch.object(module, "ensure_ability_menu_displayed")
        distributor = object.__new__(AbilityPointDistributor)
        distributor.data = self.data
        distributor.condition = mocker.Mock()
        distributor._display_kwargs = mocker.Mock(return_value={})  # pyright: ignore[reportPrivateUsage]
        distributor._disable_decision_makers = mocker.Mock()  # pyright: ignore[reportPrivateUsage]
        distributor._enable_decision_makers = mocker.Mock()  # pyright: ignore[reportPrivateUsage]
        distributor._distribute_ap = mocker.Mock()  # pyright: ignore[reportPrivateUsage]
        distributor._unreadable = None  # pyright: ignore[reportPrivateUsage]
        self.distributor = distributor
        self.distributor._prev_level = distributor._level()  # pyright: ignore[reportPrivateUsage]

    def _advance(self, *_: str) -> None:
        self.data.status_bar = next(self.readings)

    def decide(self) -> None:
        asyncio.run(self.distributor._decide())  # pyright: ignore[reportPrivateUsage]

    @property
    def opened(self) -> int:
        # Opening and closing the menu are two calls per level-up.
        return self.menu_opened.call_count


@pytest.fixture
def harness(mocker: MockerFixture) -> Callable[[list[Reading[StatusBar]]], Harness]:
    return lambda readings: Harness(mocker, readings)


def test_a_higher_level_opens_the_menu_once(harness) -> None:  # noqa: ANN001
    h = harness([read(10), read(10), read(11), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2
    h.distributor._distribute_ap.assert_called_once()  # pyright: ignore[reportPrivateUsage]
    h.menu_opened.reset_mock()
    h.decide()
    assert h.opened == 0


def test_an_unreadable_level_is_not_a_level_up(harness) -> None:  # noqa: ANN001
    h = harness([read(10), unsure(), unsure()])
    h.decide()
    h.decide()
    assert h.opened == 0


def test_an_unreadable_level_keeps_the_last_one_read(harness) -> None:  # noqa: ANN001
    h = harness([read(10), unsure(), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2


def test_an_unreadable_level_at_startup_makes_the_first_read_the_baseline(
    harness,  # noqa: ANN001
) -> None:
    h = harness([unsure(), read(10), read(11)])
    h.decide()
    assert h.opened == 0
    h.decide()
    assert h.opened == 2


def test_an_unreadable_level_is_logged_once_per_change(
    harness,  # noqa: ANN001
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = harness([read(10), unsure(), unsure(), read(10), unsure()])
    with caplog.at_level(logging.WARNING, logger=module.logger.name):
        for _ in range(4):
            h.decide()
    assert len(caplog.records) == 2
