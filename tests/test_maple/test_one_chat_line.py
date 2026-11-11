"""
One chat line is typed at a time (#488).

A Discord `WRITE` (`USER_REQUESTS`) outranks a reply (`ANTI_DETECTION`), and a
failsafe reaction ranks with it, so the Task Manager schedules any of them beside
a reply being typed. Each is a key sequence in the same chat input: run side by
side, their keys interleave into one garbled line.

Each scenario runs Main Process as it is live: the real `AsyncTaskManager`, fed
the requests their real builders make (`ChatReplies` for the reply, through
`tests/test_maple/test_chat_replies.py`'s harness; `MapleParser.write`;
`ReactionsMixin._react`), runs the real procedures. Only what leaves the process
is captured (`tests/sent_input.py`), so the keys recorded are the ones the game
would have received, in the order it would have received them.

The names and messages are invented.
"""

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from botting.controller.inputs.held_keys_ledger import HeldKeysLedger
from botting.core import ActionRequest
from botting.core.async_task_manager import AsyncTaskManager
from maple.actions import writing
from maple.decision_makers.mixins import ReactionsMixin
from maple.parsers import maple_parser
from maple.parsers.maple_parser import MapleParser
from maple.screen.chat import ChatKind
from tests import sent_input
from tests.sent_input import Event, SentInput
from tests.test_maple.test_chat_replies import (
    HANDLE,
    IGN,
    KEYS,
    Harness,
    line,
    says,
    started,
)

REPLY = "ya im busy grinding atm sry"
SPEAKER = "Bob"

Keys = list[tuple[str, Event]]


@pytest.fixture(autouse=True)
def reset_ledger() -> Iterator[None]:
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


# --- what each line sends alone ----------------------------------------------------


def _press(key: str) -> Keys:
    return [(key, "keydown"), (key, "keyup")]


def _typed(text: str) -> Keys:
    return [step for char in text for step in _press(char)]


def _send() -> Keys:
    """Enter sends the message; Enter again closes the chat input."""
    return _press("enter") + _press("enter")


def _reply_keys() -> Keys:
    """The reply alone: a whisper back to its speaker."""
    return (
        _press(KEYS["whisper"])
        + _typed(SPEAKER)
        + _press("enter")
        + _typed(REPLY)
        + _send()
    )


def _general_keys(message: str) -> Keys:
    """A `WRITE` or a reaction alone: a line on general."""
    return _press(KEYS["general"]) + _typed(message) + _send()


# --- the requests, from their real builders ----------------------------------------


def _reply_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> ActionRequest:
    """The request `ChatReplies` sends to answer a whisper."""
    h = Harness(monkeypatch, tmp_path, answers=[says(REPLY)])

    async def body() -> None:
        await started(h)
        await h.cycle(line(ChatKind.WHISPER, SPEAKER, "hi u there?"))
        await h.run(10)

    asyncio.run(body())
    [(_, request)] = h.replies
    return request


@pytest.fixture
def writes(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], ActionRequest]:
    """`WRITE <message>` from Discord, as `MapleParser` turns it into a request."""
    monkeypatch.setattr(maple_parser, "find_client", lambda: HANDLE)
    monkeypatch.setattr(writing, "_STARTED", {IGN: KEYS})
    parser = object.__new__(MapleParser)
    # The confirmation grabs the client's frame once the line is typed.
    monkeypatch.setattr(parser, "_confirmation_with_image", lambda handle: None)
    return lambda message: parser.write(message, IGN)


class _Reacting(ReactionsMixin):
    """A bot's failsafe reaction, with `send` captured."""

    def __init__(self) -> None:
        self.data = SimpleNamespace(  # pyright: ignore[reportAttributeAccessIssue]
            ign=IGN,
            handle=HANDLE,
            chat_keys=KEYS,
            current_frame=SimpleNamespace(pixels=None),
        )
        self.sent: list[ActionRequest] = []
        self.send = self.sent.append

    def __str__(self) -> str:
        return f"Rotation({IGN})"


@pytest.fixture
def reacts(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], ActionRequest]:
    """A light failsafe reaction saying `message`. The 10 second `@cooldown` is a
    rate limit, not part of what is checked, so it is passed (`__wrapped__`)."""
    reacting = _Reacting()

    def react(message: str) -> ActionRequest:
        monkeypatch.setattr(ReactionsMixin, "_light_reactions", [message])
        ReactionsMixin._react.__wrapped__(reacting, "light")  # pyright: ignore[reportFunctionMemberAccess]
        return reacting.sent[-1]

    return react


# --- Main Process -------------------------------------------------------------------


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> SentInput:
    return sent_input.install(monkeypatch, HANDLE)


def _main_process(
    sent: SentInput,
    first: ActionRequest,
    *then: ActionRequest,
    mid_line_after: int,
) -> None:
    """
    Run the Task Manager as Main Process does: `first` is queued, and each of
    `then` once `first` has sent `mid_line_after` key events, part-way through its
    line. Returns once every request's task has ended.
    """

    async def until(done: Callable[[], bool]) -> None:
        for _ in range(100_000):
            if done():
                return
            await asyncio.sleep(0)
        raise AssertionError("the Task Manager never got there")

    async def main() -> None:
        manager = AsyncTaskManager(SimpleNamespace(send=lambda item: None))  # pyright: ignore[reportArgumentType]
        running = asyncio.create_task(manager.start())
        requests = (first, *then)
        await manager.queue.put(first)
        await until(lambda: len(sent.steps) >= mid_line_after or running.done())
        for request in then:
            await manager.queue.put(request)
        await until(
            lambda: (
                running.done()
                or all(r.task is not None and r.task.done() for r in requests)
            )
        )
        if running.done():
            running.result()  # a Task Manager that stopped says why
        await manager.queue.put(None)
        await running
        assert manager.failure is None
        assert not any(r.task is not None and r.task.cancelled() for r in requests), (
            "a line was cut off"
        )

    asyncio.run(main())


# --- one line at a time -------------------------------------------------------------


def test_a_write_during_a_reply_waits_for_its_last_enter_then_types_in_full(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    writes: Callable[[str], ActionRequest],
    sent: SentInput,
) -> None:
    reply = _reply_request(monkeypatch, tmp_path)
    reply_alone = _reply_keys()

    _main_process(sent, reply, writes("brb guys"), mid_line_after=len(reply_alone) // 2)

    assert sent.keys() == reply_alone + _general_keys("brb guys")


def test_two_writes_type_one_after_the_other(
    writes: Callable[[str], ActionRequest], sent: SentInput
) -> None:
    first_alone = _general_keys("one sec")

    _main_process(
        sent,
        writes("one sec"),
        writes("ok back"),
        mid_line_after=len(first_alone) // 2,
    )

    assert sent.keys() == first_alone + _general_keys("ok back")


def test_a_failsafe_reaction_during_a_reply_waits_for_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reacts: Callable[[str], ActionRequest],
    sent: SentInput,
) -> None:
    reply = _reply_request(monkeypatch, tmp_path)
    reply_alone = _reply_keys()

    _main_process(sent, reply, reacts("wtf"), mid_line_after=len(reply_alone) // 2)

    assert sent.keys() == reply_alone + _general_keys("wtf")


def test_reactions_that_pile_up_behind_a_reply_each_type_in_full(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reacts: Callable[[str], ActionRequest],
    sent: SentInput,
) -> None:
    """A long reply outlasts the reactions' 10 s cooldown: a second reaction can
    come while the first still waits, and neither is lost."""
    reply = _reply_request(monkeypatch, tmp_path)
    reply_alone = _reply_keys()

    _main_process(
        sent,
        reply,
        reacts("wtf"),
        reacts("lag?"),
        mid_line_after=len(reply_alone) // 2,
    )

    assert sent.keys() == reply_alone + _general_keys("wtf") + _general_keys("lag?")


def test_a_reply_alone_and_a_write_alone_send_what_they_always_sent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    writes: Callable[[str], ActionRequest],
    sent: SentInput,
) -> None:
    reply = _reply_request(monkeypatch, tmp_path)

    _main_process(sent, reply, mid_line_after=0)
    _main_process(sent, writes("brb guys"), mid_line_after=0)

    assert sent.keys() == _reply_keys() + _general_keys("brb guys")
