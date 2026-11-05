"""
`ChatWatch` on stubbed `chat_lines` readings: a GM line emits `chat.gm_line` and,
when Discord is configured, rides a Discord alert with the line's image on a
no-op Action. Nothing else is sent. No client.
"""

import asyncio
import logging
from pathlib import Path

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core import ActionRequest
from botting.screen import Reading
from maple.bots.training import TrainingBot
from maple.decision_makers import chat_watch as module
from maple.decision_makers.chat_watch import ChatWatch
from maple.screen.chat import CHAT, ChatKind, ChatLine
from maple.telemetry_events import CHAT_GM_LINE


def line(kind: ChatKind, text: str | None = None, top: int = 100) -> ChatLine:
    return ChatLine(kind, np.full((16, 20, 3), 7, np.uint8), text, top)


class Harness:
    def __init__(
        self,
        mocker: MockerFixture,
        readings: list[Reading[list[ChatLine]]],
        discord: Path,
    ) -> None:
        self.readings = iter(readings)
        self.data = mocker.Mock()
        self.data.ign = "Bot"
        self.data.update_attributes.side_effect = self._advance
        self.pipe = mocker.Mock()
        watch = object.__new__(ChatWatch)
        watch.data = self.data
        watch.pipe = self.pipe
        watch.correlation_id = None
        watch._discord_config = discord  # pyright: ignore[reportPrivateUsage]
        watch._last_status = None  # pyright: ignore[reportPrivateUsage]
        self.emit = mocker.patch.object(watch, "emit")
        self.watch = watch

    def _advance(self, *names: str) -> None:
        assert names == ("current_frame", "chat_lines")
        self.data.chat_lines = next(self.readings)

    def decide(self) -> None:
        asyncio.run(self.watch._decide())  # pyright: ignore[reportPrivateUsage]

    @property
    def sent(self) -> list[ActionRequest]:
        return [call.args[0] for call in self.pipe.send.call_args_list]


@pytest.fixture
def discord(tmp_path: Path) -> Path:
    path = tmp_path / "discord.ini"
    path.write_text("[DEFAULT]\n", encoding="utf-8")
    return path


def test_a_gm_line_emits_and_alerts_with_its_image(
    mocker: MockerFixture, discord: Path
) -> None:
    gm = line(ChatKind.GM, "hello", top=634)
    h = Harness(
        mocker, [Reading.read([line(ChatKind.GENERAL, "hi"), gm], 1.0)], discord
    )
    h.decide()

    h.emit.assert_called_once_with(
        CHAT_GM_LINE, {"kind": "gm", "text": "hello", "row_top": 634}
    )
    [request] = h.sent
    assert request.discord_request is not None
    assert request.discord_request.img is gm.image
    assert "hello" in request.discord_request.msg


def test_the_alert_sends_no_input(mocker: MockerFixture, discord: Path) -> None:
    """Its Action's procedure does nothing, and takes no handle or key."""
    h = Harness(mocker, [Reading.read([line(ChatKind.GM)], 1.0)], discord)
    h.decide()
    [request] = h.sent
    assert request.args == ()
    assert request.kwargs == {}
    assert not request.block_lower_priority
    assert asyncio.run(request.procedure()) is None


def test_no_discord_alert_when_discord_isnt_configured(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    h = Harness(mocker, [Reading.read([line(ChatKind.GM)], 1.0)], tmp_path / "none.ini")
    h.decide()
    h.emit.assert_called_once()
    assert h.sent == []


@pytest.mark.parametrize(
    "kind", [k for k in ChatKind if k is not ChatKind.GM], ids=lambda k: k.value
)
def test_other_lines_raise_no_alarm(
    mocker: MockerFixture, discord: Path, kind: ChatKind
) -> None:
    h = Harness(mocker, [Reading.read([line(kind, "x")], 1.0)], discord)
    h.decide()
    h.emit.assert_not_called()
    assert h.sent == []


def test_an_unreadable_chat_raises_nothing_and_is_logged_once_per_change(
    mocker: MockerFixture, discord: Path, caplog: pytest.LogCaptureFixture
) -> None:
    readings: list[Reading[list[ChatLine]]] = [
        Reading.covered(1.0, "row"),
        Reading.covered(2.0, "row"),
        Reading.read([], 3.0),
        Reading.covered(4.0, "row"),
    ]
    h = Harness(mocker, readings, discord)
    with caplog.at_level(logging.INFO, logger=module.logger.name):
        for _ in readings:
            h.decide()
    h.emit.assert_not_called()
    assert h.sent == []
    assert len([r for r in caplog.records if "can't read the chat" in r.message]) == 2


def test_the_training_bot_runs_chat_watch_which_declares_the_chat() -> None:
    assert ChatWatch in TrainingBot._decision_makers(None)  # pyright: ignore[reportArgumentType, reportPrivateUsage]
    assert CHAT in ChatWatch.screen_readers
