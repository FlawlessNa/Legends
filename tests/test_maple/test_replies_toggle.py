"""
`Bot.replies` switches what `ChatReplies` reads, `REPLIES_ON`, and reports the
switch. The switch is a Bot-level Provider, built on by `Bot.child_init`.
"""

import pytest

from botting.core import REPLIES_ON, Bot, DecisionMaker, RepliesProvider
from botting.core.bot_data import BotData
from maple.bots.maple_bot import MapleBot
from maple.telemetry_events import CHAT_REPLIES_TOGGLED
from tests.test_maple.serving import serve


class _Bot(MapleBot):
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.ign = "Alice"
        self.data = serve(monkeypatch, "Alice").data

    @property
    def replies_on(self) -> bool:
        assert self.data is not None
        return self.data.read(REPLIES_ON)

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


def test_replies_off_switches_the_key_and_says_who_asked(
    monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, dict]]
) -> None:
    bot = _Bot(monkeypatch)

    bot.replies(False)

    assert bot.replies_on is False
    assert events == [
        (CHAT_REPLIES_TOGGLED, {"on": False, "source": "discord_replies"})
    ]


def test_a_takeover_is_replies_off_from_the_write(
    monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, dict]]
) -> None:
    bot = _Bot(monkeypatch)

    bot.takeover()

    assert bot.replies_on is False
    assert events == [(CHAT_REPLIES_TOGGLED, {"on": False, "source": "discord_write"})]


def test_replies_on_hands_back(
    monkeypatch: pytest.MonkeyPatch, events: list[tuple[str, dict]]
) -> None:
    bot = _Bot(monkeypatch)
    bot.replies(False)

    bot.replies(True)

    assert bot.replies_on is True
    assert events[-1] == (
        CHAT_REPLIES_TOGGLED,
        {"on": True, "source": "discord_replies"},
    )


class _Engine(Bot):
    """A generic Bot: what `child_init` builds before any game layer."""

    def find_handle(self) -> int:
        return 7

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return []


def test_every_bot_starts_with_replies_on() -> None:
    bot = _Engine("Alice", {})  # pyright: ignore[reportArgumentType] - no Manager needed
    bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - nothing sent

    assert any(isinstance(p, RepliesProvider) for p in bot.providers)
    assert isinstance(bot.data, BotData)
    assert bot.data.read(REPLIES_ON) is True
    assert "replies_on" not in bot.data._static  # pyright: ignore[reportPrivateUsage]
