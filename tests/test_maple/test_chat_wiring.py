"""
What the bot's DecisionMakers take from the chat reader: `ChatProvider`'s
`CHAT_LINES` and `CHAT_SHOWN`, whether the log is shown (`CheckMobsStillSpawn`),
and where the chat starts (`MobsHitting`). Stubbed readers, no client.
"""

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core.bot_data import BotData
from botting.screen import Frame, Reading, Status
from botting.utilities import Box
from maple.decision_makers import CheckMobsStillSpawn, MobsHitting
from maple.decision_makers.providers import CHAT_LINES, CHAT_SHOWN, ChatProvider
from maple.screen.chat import CHAT
from tests.test_maple.serving import serve


def frame(h: int = 300) -> Frame:
    return Frame(np.zeros((h, 400, 3), np.uint8), (400, h), 0.0, True, True)


def _chat(monkeypatch: pytest.MonkeyPatch, reader: object, current: Frame) -> BotData:
    """A Bot's data whose chat reader is `reader`, with `ChatProvider` built."""
    served = serve(monkeypatch, frames=lambda: current, chat=reader)
    served.data.build_provider(ChatProvider)
    return served.data


def test_chat_lines_is_read_only_when_refreshed(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """Each refresh returns what is new since the one before, so nothing reads
    it on its own, not even when it is set up."""
    current = frame()
    reader = mocker.Mock()
    reader.read.return_value = Reading.read([], 1.0)
    data = _chat(monkeypatch, reader, current)

    reader.read.assert_not_called()
    assert data.read(CHAT_LINES).status is Status.ABSENT
    assert data.chat_lines.status is Status.ABSENT, "unported code reads it by name"
    assert data.refresh(CHAT_LINES).value == []
    reader.read.assert_called_once_with(current)


def test_whether_the_chat_is_shown_is_read_only_when_refreshed(
    monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture
) -> None:
    """What `CheckMobsStillSpawn` asks the chat reader, served for its port."""
    current = frame()
    reader = mocker.Mock()
    reader.shown.return_value = Reading.read(True, 1.0)
    data = _chat(monkeypatch, reader, current)

    reader.shown.assert_not_called()
    assert data.read(CHAT_SHOWN).status is Status.ABSENT
    assert data.refresh(CHAT_SHOWN).value is True
    reader.shown.assert_called_once_with(current)


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


def test_mobs_hitting_hides_the_minimap_and_the_chat_as_read(
    mocker: MockerFixture,
) -> None:
    """The character found inside the minimap or the chat isn't ours: both are
    hidden, where their readers place them, in client pixels."""
    hitting = object.__new__(MobsHitting)
    hitting.data = mocker.Mock()
    hitting.data.current_frame = frame()
    minimap = Box(left=20, right=152, top=20, bottom=167)
    chat = Box(left=10, right=300, top=220, bottom=290)
    hitting.data.current_entire_minimap_box = minimap
    hitting.data.chat_reader.region.return_value = chat

    assert hitting._regions_to_hide() == [minimap, chat]  # pyright: ignore[reportPrivateUsage]

    hitting.data.current_entire_minimap_box = None
    hitting.data.chat_reader.region.return_value = None
    assert hitting._regions_to_hide() == []  # pyright: ignore[reportPrivateUsage]
