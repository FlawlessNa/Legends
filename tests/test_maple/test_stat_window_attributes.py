"""
`_create_ap_menu_attributes` adds `stat_window`, and takes speed and jump from
it only when it is `READ` with Detail open; `ensure_ability_menu_displayed`
presses the window's key until `StatWindowReader.shown` says what is wanted;
`click_then_move_off` leaves the cursor off the window it clicked.
Stubbed readers and actions, no client.
"""

import asyncio
import logging

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading
from botting.utilities import Box
from maple.actions import menus
from maple.decision_makers.mixins import MenusMixin
from maple.decision_makers.mixins import _interface_mixins as mixins
from maple.screen.stat_window import StatWindow

WINDOW = Box(left=10, right=200, top=10, bottom=290)
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
    data = _setup(mocker, Reading.read(StatWindow(0, 125, 110, {}, WINDOW), 1.0))

    assert data.speed_multiplier == 1.25
    assert data.jump_multiplier == 1.10
    assert data.stat_window.value.available_ap == 0
    assert data.has_ap_menu_attributes


@pytest.mark.parametrize(
    "reading",
    [
        Reading.read(StatWindow(0, None, None, {}, WINDOW), 1.0),
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


@pytest.mark.parametrize(
    "avoid",
    [
        WINDOW,
        Box(left=0, right=300, top=0, bottom=300),  # in the client's top-left
        Box(left=700, right=799, top=300, bottom=599),  # in its bottom-right
    ],
)
def test_the_point_off_leaves_the_cursor_clear_of_the_window(avoid: Box) -> None:
    size = menus.CURSOR_SIZE
    for _ in range(500):
        x, y = menus.point_off(avoid, 800, 600)
        assert 0 <= x < 800
        assert 0 <= y < 600
        overlaps = (
            x <= avoid.right
            and avoid.left <= x + size
            and y <= avoid.bottom
            and avoid.top <= y + size
        )
        assert not overlaps, (x, y)


def test_a_window_filling_the_client_leaves_no_point_off() -> None:
    with pytest.raises(ValueError, match="no room for the cursor"):
        menus.point_off(Box(left=0, right=799, top=0, bottom=599), 800, 600)


def test_the_cursor_is_moved_off_the_window_after_the_clicks(
    mocker: MockerFixture,
) -> None:
    calls: list[tuple[str, tuple[int, int]]] = []

    async def click(_: int, target: tuple[int, int], **__: object) -> None:
        calls.append(("click", target))

    async def move(_: int, target: tuple[int, int], *__: object) -> None:
        calls.append(("move", target))

    mocker.patch.object(menus.controller, "mouse_move_and_click", click)
    mocker.patch.object(menus.controller, "mouse_move", move)
    mocker.patch.object(menus.win32gui, "GetClientRect", return_value=(0, 0, 800, 600))

    asyncio.run(menus.click_then_move_off(1, (150, 180), WINDOW, nbr_times=3))

    assert calls[0] == ("click", (150, 180))
    kind, (x, y) = calls[1]
    assert kind == "move"
    assert x > WINDOW.right or y > WINDOW.bottom
