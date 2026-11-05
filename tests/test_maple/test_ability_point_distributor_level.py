"""
When `AbilityPointDistributor` opens the AP menu: on a level read higher or
different from the last level read. An unreadable level is not a level-up and
doesn't replace the last level read. It spends AP only on a `READ` stat window.
Stubbed `status_bar` and `stat_window` readings, no client.
"""

import asyncio
import logging
from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from botting.screen import Frame, Reading
from botting.utilities import Box
from maple.decision_makers import ability_point_distributor as module
from maple.decision_makers.ability_point_distributor import AbilityPointDistributor
from maple.screen.locator import FrameCheck
from maple.screen.stat_window import StatWindow, StatWindowReader
from maple.screen.status_bar import StatusBar
from tests.test_maple import test_screen_stat_window as synthetic

BUTTONS = {"STR": (10, 20), "DEX": (10, 38), "INT": (10, 56), "LUK": (10, 74)}


BOUNDS = Box(left=0, right=185, top=0, bottom=281)


def window(ap: int) -> Reading[StatWindow]:
    return Reading.read(StatWindow(ap, None, None, BUTTONS, BOUNDS), 1.0)


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
        self.data.stat_window = window(5)
        self.data.character.main_stat = "DEX"
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

    def _advance(self, *names: str) -> None:
        if "status_bar" in names:
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


def test_the_ap_read_is_spent_on_the_main_stat(harness) -> None:  # noqa: ANN001
    h = harness([read(10), read(11)])
    h.decide()
    h.distributor._distribute_ap.assert_called_once_with(5, BUTTONS["DEX"], BOUNDS)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    "reading",
    [
        window(0),
        Reading.covered(1.0, "not where expected: labels"),
        Reading.unsure(1.0, "AP: '1?'"),
        Reading.absent(1.0, "not found"),
    ],
)
def test_ap_is_spent_only_on_a_read_above_zero(
    harness,  # noqa: ANN001
    reading: Reading[StatWindow],
) -> None:
    h = harness([read(10), read(11)])
    h.data.stat_window = reading
    h.decide()
    h.distributor._distribute_ap.assert_not_called()  # pyright: ignore[reportPrivateUsage]
    assert h.opened == 2  # opened, then closed again


@pytest.mark.parametrize(
    ("reading", "expected"),
    [
        (window(0), True),
        (window(2), False),
        (Reading.unsure(1.0, "AP: 0, but a +1 button is drawn enabled"), False),
        (Reading.covered(1.0, "AP: 3 pixel(s) over it"), False),
    ],
)
def test_the_points_are_spent_once_a_fresh_read_shows_none_left(
    mocker: MockerFixture, reading: Reading[StatWindow], expected: bool
) -> None:
    mocker.patch.object(module, "frame_source")
    distributor = object.__new__(AbilityPointDistributor)
    distributor.data = mocker.Mock()
    distributor.data.stat_window_reader.read.return_value = reading

    assert distributor._no_ap_left() is expected  # pyright: ignore[reportPrivateUsage]


def test_the_clicks_end_with_the_cursor_moved_off_the_window(
    mocker: MockerFixture,
) -> None:
    validated = mocker.patch.object(module, "ActionWithValidation")
    distributor = object.__new__(AbilityPointDistributor)
    distributor.data = mocker.Mock()
    distributor.pipe = mocker.Mock()
    distributor.condition = mocker.Mock()
    distributor.correlation_id = None

    distributor._distribute_ap(3, BUTTONS["STR"], BOUNDS)  # pyright: ignore[reportPrivateUsage]

    (request,) = validated.return_value.execute_blocking.call_args.args
    assert request.procedure is module.click_then_move_off
    assert request.args == (distributor.data.handle, BUTTONS["STR"], BOUNDS)
    assert request.kwargs == {"nbr_times": 3, "delay": 0.15}


@pytest.mark.parametrize(("cursor_on_button", "spent"), [(True, False), (False, True)])
def test_no_ap_left_is_seen_only_with_the_cursor_off_the_buttons(
    mocker: MockerFixture, cursor_on_button: bool, spent: bool
) -> None:
    """The window as the clicks leave it: AP 0, every +1 button disabled. A
    cursor still over the button it clicked hides that button's state, so the
    read is `UNSURE` and AP 0 is never seen: why the clicks end by moving the
    cursor off the window."""
    pixels = synthetic.window(ap="0", buttons="disabled")
    if cursor_on_button:
        x, y = synthetic.MAIN_AT
        ox, oy = synthetic.UP_ORIGINS["STR"]
        pixels[y - oy + 2 : y - oy + 14, x - ox + 2 : x - ox + 10] = (255, 255, 255)
    h, w = pixels.shape[:2]
    grab = mocker.patch.object(module, "frame_source")
    grab.return_value.grab.return_value = Frame(pixels, (w, h), 0.0, True, True)
    distributor = object.__new__(AbilityPointDistributor)
    distributor.data = mocker.Mock()
    distributor.data.stat_window_reader = StatWindowReader(
        synthetic.SPRITES, FrameCheck(synthetic.SPRITES)
    )

    assert distributor._no_ap_left() is spent  # pyright: ignore[reportPrivateUsage]
