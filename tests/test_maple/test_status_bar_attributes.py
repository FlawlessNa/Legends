"""
`_create_status_bar_attributes` adds `status_bar` and leaves the bot's
`current_frame` alone: the minimap reads that frame without updating it, and
relies on the refresh threshold `MapleBot.child_init` gives it.
"""

import numpy as np
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading
from maple.decision_makers.mixins import UIMixin

THRESHOLD = 0.1


class _Consumer(UIMixin):
    def __init__(self, data: BotData) -> None:
        self.data = data


def test_the_bots_frame_keeps_its_refresh_threshold(mocker: MockerFixture) -> None:
    data = BotData("Bot")
    frame = Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), 0.0, True, True)
    data.create_attribute("current_frame", lambda: frame, threshold=THRESHOLD)
    reader = mocker.Mock()
    reader.read.return_value = Reading.unsure(0.0, "x")
    data.set_static("status_bar_reader", reader)

    _Consumer(data)._create_status_bar_attributes()  # pyright: ignore[reportPrivateUsage]
    _Consumer(data)._create_status_bar_attributes()  # pyright: ignore[reportPrivateUsage]

    assert data._managed["current_frame"].threshold == THRESHOLD  # pyright: ignore[reportPrivateUsage]
    assert data.status_bar.detail == "x"
    reader.read.assert_called_with(frame)
    assert data.has_status_bar_attributes
