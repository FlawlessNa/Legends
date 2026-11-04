"""
What the bot's DecisionMakers take from the chat reader: the `chat_lines`
attribute, whether the log is shown (`CheckMobsStillSpawn`), and where the chat
starts (`MobsHitting`). Stubbed readers, no client.
"""

import numpy as np
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from maple.decision_makers import CheckMobsStillSpawn, MobsHitting
from maple.decision_makers.mixins import UIMixin
from maple.screen.chat import CHAT


def frame(h: int = 300) -> Frame:
    return Frame(np.zeros((h, 400, 3), np.uint8), (400, h), 0.0, True, True)


class _Consumer(UIMixin):
    def __init__(self, data: BotData) -> None:
        self.data = data


def test_chat_lines_is_read_only_when_updated(mocker: MockerFixture) -> None:
    """Each update returns what is new since the one before, so nothing reads
    it on its own, not even when it is created."""
    data = BotData("Bot")
    current = frame()
    data.create_attribute("current_frame", lambda: current, threshold=0.1)
    reader = mocker.Mock()
    reader.read.return_value = Reading.read([], 1.0)
    data.set_static("chat_reader", reader)

    _Consumer(data)._create_chat_attributes()  # pyright: ignore[reportPrivateUsage]

    reader.read.assert_not_called()
    assert data.chat_lines.status is Status.ABSENT
    data.update_attribute("chat_lines")
    reader.read.assert_called_once_with(current)
    assert data.chat_lines.value == []
    assert data.has_chat_attributes


def test_mob_spawn_check_shows_and_hides_the_chat_by_the_reader(
    mocker: MockerFixture,
) -> None:
    check = object.__new__(CheckMobsStillSpawn)
    check.data = mocker.Mock()
    readings = iter(
        [Reading.read(True, 1.0), Reading.read(False, 1.0), Reading.covered(1.0, "x")]
    )
    check.data.chat_reader.shown.side_effect = lambda _: next(readings)

    shown = [check._chat_shown() for _ in range(3)]  # pyright: ignore[reportPrivateUsage]

    assert shown == [True, False, None]
    check.data.update_attribute.assert_called_with("current_frame")
    assert CHAT in CheckMobsStillSpawn.screen_readers


def test_mobs_hitting_leaves_out_the_chat_from_its_top(mocker: MockerFixture) -> None:
    hitting = object.__new__(MobsHitting)
    hitting.data = mocker.Mock()
    hitting.data.current_frame = frame(h=300)
    hitting.data.chat_reader.region.return_value = Box(
        left=10, right=300, top=220, bottom=290
    )
    assert hitting._chat_top() == 220  # pyright: ignore[reportPrivateUsage]

    hitting.data.chat_reader.region.return_value = None
    assert hitting._chat_top() == 300  # pyright: ignore[reportPrivateUsage]
    assert CHAT in MobsHitting.screen_readers
