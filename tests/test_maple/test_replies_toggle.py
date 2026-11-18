"""`Bot.replies` sets what `ChatReplies` reads and reports the switch."""

import pytest

from botting.core.bot_data import BotData
from maple.bots.maple_bot import MapleBot
from maple.telemetry_events import CHAT_REPLIES_TOGGLED


class _Bot(MapleBot):
    def __init__(self) -> None:
        self.ign = "Alice"
        self.data = BotData("Alice")
        self.data.set_static("replies_on", True)

    @property
    def replies_on(self) -> bool:
        assert self.data is not None
        return self.data.replies_on

    def _decision_makers(self) -> list:
        return []


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict]]:
    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "maple.bots.maple_bot.emit_event",
        lambda correlation, event, payload, logger_name=None: seen.append(
            (event, dict(payload))
        ),
    )
    return seen


def test_replies_off_sets_the_static_and_says_who_asked(
    events: list[tuple[str, dict]],
) -> None:
    bot = _Bot()

    bot.replies(False)

    assert bot.replies_on is False
    assert events == [
        (CHAT_REPLIES_TOGGLED, {"on": False, "source": "discord_replies"})
    ]


def test_a_takeover_is_replies_off_from_the_write(
    events: list[tuple[str, dict]],
) -> None:
    bot = _Bot()

    bot.takeover()

    assert bot.replies_on is False
    assert events == [(CHAT_REPLIES_TOGGLED, {"on": False, "source": "discord_write"})]


def test_replies_on_hands_back(events: list[tuple[str, dict]]) -> None:
    bot = _Bot()
    bot.replies(False)

    bot.replies(True)

    assert bot.replies_on is True
    assert events[-1] == (
        CHAT_REPLIES_TOGGLED,
        {"on": True, "source": "discord_replies"},
    )
