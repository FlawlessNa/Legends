"""
`StatusBarProvider` serves `status_bar` and leaves the bot's frame alone: the
minimap reads that frame without refreshing it, and relies on the refresh
threshold `ClientProvider` gives it. An unported DecisionMaker asks for it with
`_create_status_bar_attributes`, as often as it likes.
"""

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.screen import Frame, Reading
from maple.decision_makers.mixins import UIMixin
from maple.decision_makers.providers import ClientProvider, StatusBarProvider
from tests.test_maple.serving import serve


class _Consumer(UIMixin):
    def __init__(self, data: object) -> None:
        self.data = data  # pyright: ignore[reportAttributeAccessIssue] - a BotData


def test_the_bots_frame_keeps_its_refresh_threshold(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    frame = Frame(np.zeros((4, 4, 3), np.uint8), (4, 4), 0.0, True, True)
    reader = mocker.Mock()
    reader.read.return_value = Reading.unsure(0.0, "x")
    served = serve(monkeypatch, frames=lambda: frame, status_bar=reader)
    data = served.data

    _Consumer(data)._create_status_bar_attributes()  # pyright: ignore[reportPrivateUsage]
    _Consumer(data)._create_status_bar_attributes()  # pyright: ignore[reportPrivateUsage]

    assert data._managed["frame"].threshold == ClientProvider.FRAME_REFRESH  # pyright: ignore[reportPrivateUsage]
    assert data.status_bar.detail == "x"
    reader.read.assert_called_once_with(frame)
    assert [type(p) for p in served.providers].count(StatusBarProvider) == 1
