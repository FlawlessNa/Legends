"""
`_create_ap_menu_attributes` adds `stat_window`, and takes speed and jump from
it only when it is `READ` with Detail open; `ensure_ability_menu_displayed`
presses the window's key until `StatWindowReader.shown` says what is wanted.
Stubbed readers and actions, no client.
"""

import logging

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading
from maple.actions import menus
from maple.decision_makers.mixins import MenusMixin
from maple.decision_makers.mixins import _interface_mixins as mixins
from maple.screen.stat_window import StatWindow

FRAME = Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), 0.0, True, True)


class _Consumer(MenusMixin):
    def __init__(self, data: BotData, mocker: MockerFixture) -> None:
        self.data = data
        self.pipe = mocker.Mock()
        self._proxies = mocker.Mock()


def _setup(mocker: MockerFixture, reading: Reading[StatWindow]) -> BotData:
    data = BotData("Bot")
    data.create_attribute("current_frame", lambda: FRAME, threshold=0.1)
    data.set_static("handle", 1)
    data.set_static("speed_multiplier", 1.0)
    data.set_static("jump_multiplier", 1.0)
    reader = mocker.Mock()
    reader.read.return_value = reading
    data.set_static("stat_window_reader", reader)
    mocker.patch.object(mixins, "ensure_ability_menu_displayed")
    _Consumer(data, mocker)._create_ap_menu_attributes(mocker.Mock())  # pyright: ignore[reportPrivateUsage]
    return data


def test_speed_and_jump_are_read_from_detail(mocker: MockerFixture) -> None:
    data = _setup(mocker, Reading.read(StatWindow(0, 125, 110, {}), 1.0))

    assert data.speed_multiplier == 1.25
    assert data.jump_multiplier == 1.10
    assert data.stat_window.value.available_ap == 0
    assert data.has_ap_menu_attributes


@pytest.mark.parametrize(
    "reading",
    [
        Reading.read(StatWindow(0, None, None, {}), 1.0),
        Reading.covered(1.0, "Detail: not where expected: top"),
        Reading.unsure(1.0, "speed: '1O0%'"),
    ],
)
def test_speed_and_jump_unread_keep_the_profiles(
    mocker: MockerFixture,
    caplog: pytest.LogCaptureFixture,
    reading: Reading[StatWindow],
) -> None:
    with caplog.at_level(logging.WARNING, logger=mixins.logger.name):
        data = _setup(mocker, reading)

    assert (data.speed_multiplier, data.jump_multiplier) == (1.0, 1.0)
    assert "can't read speed and jump" in caplog.text


@pytest.mark.parametrize(
    ("shown", "wanted", "validated"),
    [
        (True, True, True),
        (False, True, False),
        (None, True, False),
        (False, False, True),
        (True, False, False),
        (None, False, False),
    ],
)
def test_the_key_is_pressed_until_the_window_is_as_wanted(
    mocker: MockerFixture, shown: bool | None, wanted: bool, validated: bool
) -> None:
    mocker.patch.object(menus, "frame_source")
    action = mocker.patch.object(menus, "ActionWithValidation")
    reader = mocker.Mock()
    reader.shown.return_value = shown

    menus.ensure_ability_menu_displayed(
        "id", 1, "ign", mocker.Mock(), reader, mocker.Mock(), 2.0, wanted
    )

    validator = action.call_args.args[1]
    assert validator() is validated
    action.return_value.execute_blocking.assert_called_once()
