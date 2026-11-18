"""
`ChatReplies`, the real DecisionMaker, driven by scripted chat lines and a
scripted model with a set latency, on a virtual clock. Each rule is checked
against what it sends to Main Process: the `ActionRequest`s, and the Discord
strings. No client, no network, and no Main Process: a reply's callback is run
by the test, as the Task Manager would once the reply is typed.

The names and messages are invented.
"""

import asyncio
import heapq
import itertools
import queue
import random
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import BaseModel

from botting.communications.messages import QuietMessage
from botting.controller import TypingPace
from botting.core import ActionRequest, BotData, ProxyFactory
from botting.llm import ModelAnswer
from botting.screen import Reading
from maple.actions import DEFAULT_CHAT_KEYS, priorities, reply_in_chat
from maple.bots.training import TrainingBot
from maple.chat_replies.relay import _Answer
from maple.decision_makers import chat_replies as module
from maple.decision_makers.chat_replies import (
    PLAYER_INTERVAL,
    READ_CAP,
    SESSION_CALLS,
    ChatReplies,
    close_the_game,
    read_delay,
)
from maple.screen.chat import CHAT, ChatKind, ChatLine
from maple.screen.font import UNREAD
from maple.screen.sprites import StartupRefused
from maple.telemetry_events import (
    CHAT_GM_LINE,
    CHAT_LINE_ADDRESSED,
    CHAT_REPLY_FAILED,
    CHAT_REPLY_LIMITED,
    CHAT_REPLY_SENT,
    CHAT_REPLY_SILENT,
)

IGN = "Mapler"
HANDLE = 4242
KEYS = {**DEFAULT_CHAT_KEYS, "general": "g"}
TRAINING = ("Rotation", "MobsHitting", "PetFood", "ChatReplies")


# --- virtual time -------------------------------------------------------------------


class Clock:
    """Seconds that pass only when the test says so. `sleep` waits on it."""

    def __init__(self) -> None:
        self.now = 0.0
        self._waiters: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        future = asyncio.get_running_loop().create_future()
        heapq.heappush(
            self._waiters, (self.now + max(seconds, 0.0), next(self._order), future)
        )
        await future

    async def advance(self, seconds: float) -> None:
        """Let `seconds` pass, waking each sleeper at its own time."""
        target = self.now + seconds
        while True:
            await _settle()
            if not self._waiters or self._waiters[0][0] > target:
                break
            at, _, future = heapq.heappop(self._waiters)
            self.now = at
            if not future.done():
                future.set_result(None)
        self.now = target
        await _settle()


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


# --- the model ------------------------------------------------------------------------


def says(reply: str | None) -> ModelAnswer:
    return ModelAnswer("ok", _Answer(reply=reply), "", 5)


class ScriptedModel:
    """Answers each request after `latency` seconds of the clock, with the next
    scripted answer ("hey" once they run out)."""

    def __init__(
        self,
        clock: Clock,
        latency: float,
        answers: list[ModelAnswer],
        cause: str | None,
    ) -> None:
        self.clock = clock
        self.latency = latency
        self.answers = answers
        self.cause = cause
        self.asked: list[tuple[float, str, str | None]] = []

    async def ask(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        correlation_id: str | None = None,
    ) -> ModelAnswer:
        self.asked.append((self.clock.now, user, correlation_id))
        await self.clock.sleep(self.latency)
        return self.answers.pop(0) if self.answers else says("hey")

    async def check(self) -> str | None:
        return self.cause


# --- the chat -------------------------------------------------------------------------


def line(
    kind: ChatKind,
    speaker: str | None,
    message: str | None,
    *,
    outgoing: bool = False,
    continues: bool = False,
    text: str | None = None,
) -> ChatLine:
    if text is None and message is not None:
        text = message if speaker is None else f"{speaker} : {message}"
    return ChatLine(
        kind,
        np.full((16, 20, 3), 7, np.uint8),
        text,
        600,
        speaker,
        message,
        outgoing,
        continues,
    )


class _Reader:
    """The chat reader: each read returns the lines the test queued since."""

    def __init__(self) -> None:
        self.queued: list[ChatLine] = []

    def read(self, frame: object) -> Reading[list[ChatLine]]:
        lines, self.queued = self.queued, []
        return Reading.read(lines, 0.0)


@dataclass
class _Pipe:
    clock: Clock
    sent: list[tuple[float, object]] = field(default_factory=list)

    def send(self, item: object) -> None:
        self.sent.append((self.clock.now, item))


def _proxy(
    self: ProxyFactory,
    key: str,
    primitive_type: str,
    shared: bool,
    *args: Any,  # noqa: ANN401
    **kwargs: Any,  # noqa: ANN401
) -> object:
    made = (
        queue.Queue(*args, **kwargs)
        if primitive_type == "Queue"
        else getattr(threading, primitive_type)(*args, **kwargs)
    )
    self._meta[key] = made  # pyright: ignore[reportPrivateUsage]
    return made


class Harness:
    """One `ChatReplies`, its chat, its model and what it sends."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        *,
        latency: float = 0.5,
        answers: list[ModelAnswer] | None = None,
        cause: str | None = None,
        chat_replies: bool = True,
        discord: bool = True,
        jitter: float = 1.0,
    ) -> None:
        monkeypatch.setattr(ProxyFactory, "_request", _proxy)
        monkeypatch.setattr(module, "discord_mention", lambda: "<@42>")
        self.clock = Clock()
        self.model = ScriptedModel(self.clock, latency, list(answers or []), cause)
        self.reader = _Reader()
        self.pipe = _Pipe(self.clock)
        self.data = BotData(IGN)
        self.data.set_static("handle", HANDLE)
        self.data.set_static("replies_on", True)
        self.data.set_static("chat_keys", KEYS)
        self.data.set_static("decision_maker_names", TRAINING)
        self.data.set_static("chat_reader", self.reader)
        self.data.create_attribute("current_frame", lambda: None)
        config = tmp_path / "discord.ini"
        if discord:
            config.write_text("[DEFAULT]\n", encoding="utf-8")
        self.metadata: dict[str, object] = {}
        rng = random.Random(0)
        rng.uniform = lambda a, b: jitter  # type: ignore[method-assign]
        self.dm = ChatReplies(
            self.metadata,  # pyright: ignore[reportArgumentType]
            self.data,
            self.pipe,  # pyright: ignore[reportArgumentType]
            chat_replies=chat_replies,
            discord_config=config,
            model_factory=lambda: self.model,
            clock=self.clock,
            sleep=self.clock.sleep,
            rng=rng,
        )
        self.events: list[tuple[str, dict[str, Any], str | None]] = []
        monkeypatch.setattr(
            self.dm,
            "emit",
            lambda event, payload=None, correlation_id=None: self.events.append(
                (event, dict(payload or {}), correlation_id or self.dm.correlation_id)
            ),
        )
        self.disabled: list[str] = []
        self.enabled: list[str] = []
        monkeypatch.setattr(
            self.dm,
            "_disable_decision_makers",
            lambda *names, **kw: self.disabled.extend(names),
        )
        monkeypatch.setattr(
            self.dm,
            "_enable_decision_makers",
            lambda *names, **kw: self.enabled.extend(names),
        )
        self._cycle = itertools.count(1)

    async def cycle(self, *lines: ChatLine, then: float = 0.5) -> None:
        """One decision, with `lines` new in the chat, then `then` seconds."""
        self.reader.queued.extend(lines)
        self.dm.correlation_id = f"cycle-{next(self._cycle)}"
        await self.dm._decide()  # pyright: ignore[reportPrivateUsage]
        await self.clock.advance(then)

    async def run(self, seconds: float) -> None:
        for _ in range(round(seconds / 0.5)):
            await self.cycle()

    # What was sent

    @property
    def requests(self) -> list[tuple[float, ActionRequest]]:
        return [(t, r) for t, r in self.pipe.sent if isinstance(r, ActionRequest)]

    @property
    def replies(self) -> list[tuple[float, ActionRequest]]:
        return [(t, r) for t, r in self.requests if r.procedure is reply_in_chat]

    @property
    def posted(self) -> list[str]:
        return [m for _, m in self.pipe.sent if isinstance(m, str)]

    def events_of(self, event: str) -> list[dict[str, Any]]:
        return [payload for e, payload, _ in self.events if e == event]

    def typed(self, request: ActionRequest) -> None:
        """Main Process typed the reply: its callbacks run."""
        for callback in request.callbacks:
            callback()


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[..., Harness]:
    return lambda **kwargs: Harness(monkeypatch, tmp_path, **kwargs)


def scenario(body: Callable[[], Any]) -> None:
    asyncio.run(body())


async def started(h: Harness) -> None:
    """The first read: what was on screen before the session."""
    await h.cycle()


# --- one reply per burst --------------------------------------------------------------


def test_a_whisper_is_answered_on_whisper_with_the_characters_keys(
    harness: Callable[..., Harness],
) -> None:
    h = harness(answers=[says("ya")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi u there?"))
        await h.run(10)

    scenario(body)
    [(_, request)] = h.replies
    handle, text, channel, whisper_to, pace = request.args
    assert (handle, text, channel, whisper_to) == (HANDLE, "ya", "whisper", "Bob")
    assert isinstance(pace, TypingPace)
    assert request.kwargs == {"keys": KEYS}
    assert request.priority == priorities.ANTI_DETECTION
    assert request.block_lower_priority
    assert request.cancel_tasks == [
        f"Rotation({IGN})",
        f"MobsHitting({IGN})",
        f"TelecastMobsHitting({IGN})",
    ]


def test_a_general_line_naming_us_is_answered_on_general(
    harness: Callable[..., Harness],
) -> None:
    h = harness(answers=[says("sup")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.GENERAL, "Ann", "hey mapler"))
        await h.run(10)

    scenario(body)
    [(_, request)] = h.replies
    assert request.args[2:4] == ("general", None)
    [addressed] = h.events_of(CHAT_LINE_ADDRESSED)
    assert addressed == {"seq": 1, "kind": "general", "address": "must"}


def test_one_reply_answers_everything_one_player_said(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=1.0)

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.WHISPER, "Bob", "hi"),
            line(ChatKind.WHISPER, "Bob", "u there?"),
        )
        await h.run(15)

    scenario(body)
    assert len(h.replies) == 1
    [(_, user, _)] = h.model.asked
    assert "Entries to answer: 1, 2" in user


def test_a_line_between_two_others_left_to_the_model_may_get_nothing(
    harness: Callable[..., Harness],
) -> None:
    h = harness(answers=[says(None)])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.GENERAL, "Ann", "lol same"))
        await h.run(10)

    scenario(body)
    assert h.replies == []
    assert h.events_of(CHAT_REPLY_SILENT) == [{"seq": 1, "address": "judge"}]
    assert h.posted == ["[general] Ann: lol same → (silent)"]
    assert isinstance(h.posted[0], QuietMessage)


def test_our_own_lines_are_never_answered(harness: Callable[..., Harness]) -> None:
    h = harness()

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.GENERAL, IGN, "brb"),
            line(ChatKind.WHISPER, "Bob", "ya", outgoing=True),
        )
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.events_of(CHAT_LINE_ADDRESSED) == []


def test_lines_on_screen_before_the_session_are_never_answered(
    harness: Callable[..., Harness],
) -> None:
    h = harness()

    async def body() -> None:
        await h.cycle(line(ChatKind.WHISPER, "Bob", "u there?"))
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.replies == []


# --- the read delay -------------------------------------------------------------------


@pytest.mark.parametrize("jitter", [0.7, 1.0, 1.3])
def test_the_reply_waits_for_the_read_delay_measured_from_the_line(
    harness: Callable[..., Harness], jitter: float
) -> None:
    message = "hey can u help me with a quest"
    h = harness(latency=0.5, jitter=jitter, answers=[says("sry busy")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", message), then=0.0)
        await h.run(15)

    scenario(body)
    appeared = 0.5
    delay = min(READ_CAP, (2.0 + 0.060 * len(message)) * jitter)
    [(sent_at, _)] = h.replies
    assert sent_at == pytest.approx(appeared + delay)
    [sent] = h.events_of(CHAT_REPLY_SENT)
    assert sent["model_ms"] == 500
    assert sent["wait_ms"] == round((delay - 0.5) * 1000)


def test_a_model_slower_than_the_delay_is_sent_at_once(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=6.0, answers=[says("ya")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"), then=0.0)
        await h.run(15)

    scenario(body)
    [(sent_at, _)] = h.replies
    assert read_delay(2, 1.0) < 6.0
    assert sent_at == pytest.approx(0.5 + 6.0)
    [sent] = h.events_of(CHAT_REPLY_SENT)
    assert (sent["model_ms"], sent["wait_ms"]) == (6000, 0)


def test_the_read_delay_is_capped() -> None:
    assert read_delay(500, 1.3) == READ_CAP
    assert read_delay(0, 1.0) == 2.0


def test_training_goes_on_until_the_send(harness: Callable[..., Harness]) -> None:
    """Nothing reaches Main Process before the reply: no stop, no key."""
    h = harness(latency=0.5, answers=[says("ya")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi there friend"))
        await h.run(1.5)
        assert h.pipe.sent == []
        await h.run(10)

    scenario(body)
    assert len(h.replies) == 1


# --- one reply in flight, and its echo ------------------------------------------------


def test_one_reply_in_flight_at_a_time(harness: Callable[..., Harness]) -> None:
    h = harness(latency=3.0)

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.WHISPER, "Bob", "hi"), line(ChatKind.PARTY, "Ann", "yo")
        )
        await h.run(2)
        assert len(h.model.asked) == 1
        await h.run(10)
        assert len(h.replies) == 1, "the second waits for the first to be typed"
        h.typed(h.replies[0][1])
        await h.run(10)

    scenario(body)
    assert len(h.replies) == 2


def test_the_echo_of_our_reply_is_ours_even_with_its_speaker_misread(
    harness: Callable[..., Harness],
) -> None:
    """Read while the reply is still being typed, before Main Process says it
    was: held until the echo is registered, then known for ours."""
    h = harness(answers=[says("np gl")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.GENERAL, "Ann", "thx mapler"))
        await h.run(10)
        [(_, request)] = h.replies
        # Misread as no one's name, so only the echo tells it is ours.
        await h.cycle(line(ChatKind.GENERAL, "Wapjer", "np gl"))
        h.typed(request)
        await h.run(30)

    scenario(body)
    assert len(h.model.asked) == 1
    assert len(h.replies) == 1


# --- limits ---------------------------------------------------------------------------


def test_one_exchange_per_player_per_ten_seconds(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=0.5)

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(5)
        h.typed(h.replies[0][1])
        await h.cycle(line(ChatKind.WHISPER, "bob", "u there?"))
        await h.run(30)

    scenario(body)
    (first, _), (second, _) = h.replies
    assert second - first >= PLAYER_INTERVAL


def test_past_the_sessions_model_calls_the_game_is_closed(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=0.5, answers=[says(None)] * SESSION_CALLS)

    async def body() -> None:
        await started(h)
        for i in range(SESSION_CALLS + 1):
            await h.cycle(line(ChatKind.GENERAL, f"P{i:02d}", "lol"))
            await h.run(1)

    scenario(body)
    assert len(h.model.asked) == SESSION_CALLS
    assert h.events_of(CHAT_REPLY_LIMITED) == [{"calls_in_window": SESSION_CALLS}]
    [(_, request)] = [(t, r) for t, r in h.requests if r.procedure is close_the_game]
    assert request.args == (HANDLE,)
    assert request.priority == priorities.KILL_SWITCH
    assert request.block_lower_priority
    assert request.discord_request is not None
    assert request.discord_request.msg.startswith("<@42> ")
    assert h.replies == []


def test_the_limit_counts_a_sliding_window(harness: Callable[..., Harness]) -> None:
    h = harness(latency=0.5, answers=[says(None)] * (SESSION_CALLS + 1))

    async def body() -> None:
        await started(h)
        for i in range(SESSION_CALLS):
            await h.cycle(line(ChatKind.GENERAL, f"P{i:02d}", "lol"))
            await h.run(1)
        await h.run(600)
        await h.cycle(line(ChatKind.GENERAL, "Late", "lol"))
        await h.run(2)

    scenario(body)
    assert len(h.model.asked) == SESSION_CALLS + 1
    assert h.events_of(CHAT_REPLY_LIMITED) == []


def test_closing_the_game_releases_the_keys_closes_it_and_ends_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        module.controller, "release_all", lambda h: calls.append(("release", h))
    )
    monkeypatch.setattr(module, "close_client", lambda h: calls.append(("close", h)))

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(close_the_game(HANDLE))
    assert calls == [("release", HANDLE), ("close", HANDLE)]


def test_the_session_ends_even_when_the_game_wont_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module.controller, "release_all", lambda h: None)

    def refuse(handle: int) -> None:
        raise module.ClientNotClosed("still there")

    monkeypatch.setattr(module, "close_client", refuse)

    with pytest.raises(KeyboardInterrupt):
        asyncio.run(close_the_game(HANDLE))


# --- bursts that get no reply ---------------------------------------------------------


@pytest.mark.parametrize("speaker", [None, f"B{UNREAD}b"], ids=["none", "unread"])
def test_a_whisper_with_no_sender_read_is_refused_without_asking(
    harness: Callable[..., Harness], speaker: str | None
) -> None:
    h = harness()

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.WHISPER, speaker, "hi"), line(ChatKind.WHISPER, speaker, "yo")
        )
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.replies == []
    assert h.events_of(CHAT_REPLY_FAILED) == [{"seq": 2, "reason": "no_target"}]


def test_a_burst_with_no_message_read_is_never_answered(
    harness: Callable[..., Harness],
) -> None:
    """A `continues` row with nothing above it: no speaker, no message, but it
    names us, so it is `MUST`."""
    h = harness()

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.GENERAL, None, None, continues=True, text="hey mapler")
        )
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.replies == []
    assert h.events_of(CHAT_REPLY_FAILED) == [{"seq": 1, "reason": "nothing_read"}]


def test_a_wrapped_line_is_one_line_answered_in_full(
    harness: Callable[..., Harness],
) -> None:
    h = harness()

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.GENERAL, "Ann", "hey do u know where"),
            line(ChatKind.GENERAL, None, None, continues=True, text="mapler went"),
        )
        await h.run(10)

    scenario(body)
    assert h.events_of(CHAT_LINE_ADDRESSED) == [
        {"seq": 1, "kind": "general", "address": "must"}
    ]
    [(_, user, _)] = h.model.asked
    assert "[1 · general · Ann] hey do u know where mapler went" in user
    assert len(h.replies) == 1


def test_a_model_failure_is_reported_and_posted(
    harness: Callable[..., Harness],
) -> None:
    h = harness(answers=[ModelAnswer("timeout", None, "slow", 10_000)])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(10)

    scenario(body)
    assert h.replies == []
    assert h.events_of(CHAT_REPLY_FAILED) == [{"seq": 1, "reason": "model_timeout"}]
    assert h.posted == ["[whisper] Bob: hi → (no reply: model timeout: slow)"]


def test_a_silence_under_must_is_reported(harness: Callable[..., Harness]) -> None:
    h = harness(answers=[says(None)])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(10)

    scenario(body)
    assert h.events_of(CHAT_REPLY_SILENT) == [{"seq": 1, "address": "must"}]


def test_no_name_or_message_in_any_event(harness: Callable[..., Harness]) -> None:
    h = harness(answers=[says("ya"), says(None), ModelAnswer("error", None, "Bob", 1)])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "secret words"))
        await h.run(10)
        h.typed(h.replies[0][1])
        await h.cycle(line(ChatKind.GENERAL, "Ann", "other words"))
        await h.run(10)
        await h.cycle(line(ChatKind.PARTY, "Cyd", "more words"))
        await h.run(10)

    scenario(body)
    assert {e for e, _, _ in h.events} >= {
        CHAT_LINE_ADDRESSED,
        CHAT_REPLY_SENT,
        CHAT_REPLY_SILENT,
        CHAT_REPLY_FAILED,
    }
    for event, payload, _ in h.events:
        for value in payload.values():
            assert not any(
                word in str(value) for word in ("Bob", "Ann", "Cyd", "words", "ya")
            ), (event, payload)


def test_a_reply_carries_the_correlation_id_of_the_decision_that_took_it(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=2.0)

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(10)

    scenario(body)
    [(_, request)] = h.replies
    [(_, _, asked_for)] = h.model.asked
    assert asked_for == "cycle-2"
    [sent] = [cid for e, _, cid in h.events if e == CHAT_REPLY_SENT]
    assert sent == "cycle-2"
    # Stamped by `send`, as the pipe would carry it.
    assert request.correlation_id == "cycle-2"


# --- takeover -------------------------------------------------------------------------


def test_replies_off_reads_and_posts_but_never_answers_even_once_back_on(
    harness: Callable[..., Harness],
) -> None:
    h = harness()

    async def body() -> None:
        await started(h)
        h.data.set_static("replies_on", False)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(10)
        h.data.set_static("replies_on", True)
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.replies == []
    assert h.posted == ["[whisper] Bob: hi → (replies off)"]
    assert h.events_of(CHAT_LINE_ADDRESSED) == [
        {"seq": 1, "kind": "whisper", "address": "must"}
    ]


def test_a_takeover_between_the_models_answer_and_the_send_cancels_the_reply(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=0.5, answers=[says("ya")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi there"))
        await h.run(1)
        assert len(h.model.asked) == 1
        h.dm.data.set_static("replies_on", False)  # a Discord WRITE's TAKEOVER
        await h.run(10)
        h.dm.data.set_static("replies_on", True)
        await h.run(10)

    scenario(body)
    assert h.replies == []
    assert h.events_of(CHAT_REPLY_FAILED) == [{"seq": 1, "reason": "replies_off"}]
    assert len(h.model.asked) == 1, "never answered late"


def test_lines_left_pending_when_replies_go_off_are_given_up(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=5.0)

    async def body() -> None:
        await started(h)
        await h.cycle(
            line(ChatKind.WHISPER, "Bob", "hi"), line(ChatKind.PARTY, "Ann", "yo")
        )
        await h.run(1)
        h.dm.data.set_static("replies_on", False)
        await h.run(10)
        h.dm.data.set_static("replies_on", True)
        await h.run(20)

    scenario(body)
    assert len(h.model.asked) == 1
    assert h.replies == []
    assert {p["seq"] for p in h.events_of(CHAT_REPLY_FAILED)} == {1, 2}


def test_chat_replies_false_checks_nothing_and_never_answers(
    harness: Callable[..., Harness],
) -> None:
    h = harness(chat_replies=False, cause="no credentials")

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(10)

    scenario(body)
    assert h.model.asked == []
    assert h.pipe.sent == []


# --- a GM -----------------------------------------------------------------------------


def gm_line() -> ChatLine:
    return line(ChatKind.GM, "Zed", "are you there?")


@pytest.mark.parametrize(
    "setup",
    [
        {},
        {"chat_replies": False},
        {"answers": [ModelAnswer("error", None, "down", 1)]},
        {"latency": 30.0},
    ],
    ids=["replies on", "replies off", "model failing", "model slow"],
)
def test_a_gm_line_raises_the_alarm_at_once_and_stops_training(
    harness: Callable[..., Harness], setup: dict[str, Any]
) -> None:
    h = harness(**setup)

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, "Bob", "hi"))
        await h.cycle(gm_line(), then=0.0)

    scenario(body)
    [alarm] = h.events_of(CHAT_GM_LINE)
    assert alarm["kind"] == "gm"
    [(_, alert)] = [(t, r) for t, r in h.requests if r.identifier.endswith("GM alert")]
    assert alert.discord_request is not None
    assert h.disabled == ["Rotation", "MobsHitting", "PetFood"]


def test_a_gm_is_answered_first_with_the_gm_section_and_rings(
    harness: Callable[..., Harness],
) -> None:
    h = harness(latency=0.5, answers=[says("Yes, I am here.")])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.GENERAL, "Ann", "lol"), gm_line())
        await h.run(10)

    scenario(body)
    [(_, user, _)] = h.model.asked
    assert "They are from a GM" in user
    [(_, request)] = h.replies
    assert request.args[1:4] == ("Yes, I am here.", "general", None)
    assert "<@42> [gm] Zed: are you there? → Yes, I am here." in h.posted


def test_a_gms_later_whisper_is_a_gm_line_too(harness: Callable[..., Harness]) -> None:
    h = harness(chat_replies=False)

    async def body() -> None:
        await started(h)
        await h.cycle(gm_line())
        h.disabled.clear()
        h.dm.on_resume()
        await h.cycle(line(ChatKind.WHISPER, "Zed", "hello?"))

    scenario(body)
    assert h.disabled == ["Rotation", "MobsHitting", "PetFood"]


def test_resume_gives_back_exactly_what_the_gm_stopped(
    harness: Callable[..., Harness],
) -> None:
    h = harness(chat_replies=False)

    async def body() -> None:
        await started(h)
        await h.cycle(gm_line())
        await h.cycle(gm_line())

    scenario(body)
    assert h.disabled == ["Rotation", "MobsHitting", "PetFood"], "once"
    assert h.dm.on_resume() == ("Rotation", "MobsHitting", "PetFood")
    assert h.enabled == ["Rotation", "MobsHitting", "PetFood"]
    assert h.dm.on_resume() == (), "a RESUME with no GM gives back nothing"
    assert h.enabled == ["Rotation", "MobsHitting", "PetFood"]


def test_no_discord_alert_or_post_when_discord_isnt_configured(
    harness: Callable[..., Harness],
) -> None:
    h = harness(discord=False, answers=[says("ya")])

    async def body() -> None:
        await started(h)
        await h.cycle(gm_line(), line(ChatKind.WHISPER, "Bob", "hi"))
        await h.run(20)

    scenario(body)
    assert h.events_of(CHAT_GM_LINE)
    assert h.posted == []
    assert all(r.discord_request is None for _, r in h.requests)


# --- startup --------------------------------------------------------------------------


def test_without_the_model_the_start_is_refused_naming_the_cause(
    harness: Callable[..., Harness],
) -> None:
    with pytest.raises(StartupRefused, match="claude-haiku-5-5.*no credentials"):
        harness(cause="AuthenticationError: no credentials")


def test_unloadable_instructions_refuse_the_start(
    harness: Callable[..., Harness], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(ign: str) -> None:
        raise module.InstructionsError("no '## GM' section")

    monkeypatch.setattr(module, "load_instructions", broken)

    with pytest.raises(StartupRefused, match="'## GM'.*chat_replies: false"):
        harness()


def test_the_training_bot_runs_chat_replies_which_declares_the_chat() -> None:
    assert ChatReplies in TrainingBot._decision_makers(None)  # pyright: ignore[reportArgumentType, reportPrivateUsage]
    assert CHAT in ChatReplies.screen_readers
