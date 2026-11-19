"""
A GM line stops the training of the bot it was read on, and no other (#489).

Two Bots in one session, each a training loop and the real `ChatReplies`, with
the real Supervisor on the real Bot lifecycle, and each Bot's Providers built as
`child_init` builds them. The Main
Process proxies are in-process primitives in one metadata dict, which every
Bot shares as Engines share the Manager's: a key already made is handed back,
not made again. The chat is scripted, and replying is off, so no model is
asked; the GM stop runs with replies off as with them on.

The training loop stands in for `Rotation`: `ChatReplies` pauses it as one of
its `GM_STOPS`, as it would every DecisionMaker of the package.

The names are invented.
"""

import asyncio
import concurrent.futures
import queue
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from botting.core import Bot, DecisionMaker, ProxyFactory
from botting.screen import Reading
from maple.decision_makers import chat_replies
from maple.decision_makers.chat_replies import ChatReplies
from maple.screen.chat import ChatKind, ChatLine
from tests.test_maple.serving import serve


class Training(DecisionMaker):
    """A training loop, as `Rotation` is: it only has to run, once."""

    _throttle = 0.01

    async def _decide(self) -> None:
        pass


class _Reader:
    """The chat reader: each read returns the lines the test queued since."""

    def __init__(self) -> None:
        self.queued: list[ChatLine] = []

    def read(self, frame: object) -> Reading[list[ChatLine]]:
        lines, self.queued = self.queued, []
        return Reading.read(lines, 0.0)


class _Pipe:
    def send(self, item: object) -> None:
        pass


class _Bot(Bot):
    def find_handle(self) -> int:
        return 1

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [Training, ChatReplies]


def _gm_line() -> ChatLine:
    return ChatLine(
        ChatKind.GM,
        np.full((16, 20, 3), 7, np.uint8),
        "GMZed : hello there",
        600,
        "GMZed",
        "hello there",
        False,
        False,
    )


@pytest.fixture(autouse=True)
def training_is_stopped_by_a_gm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_replies, "GM_STOPS", (*chat_replies.GM_STOPS, Training))
    monkeypatch.setattr(ChatReplies, "pauses", (*ChatReplies.pauses, Training))


@pytest.fixture
def metadata(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    meta: dict[str, object] = {}

    def proxy(
        self: ProxyFactory,
        key: str,
        primitive_type: str,
        shared: bool,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> object:
        if shared and key in meta:
            return meta[key]
        kind = (
            queue.Queue
            if primitive_type == "Queue"
            else getattr(threading, primitive_type)
        )
        made = kind(*args, **kwargs)
        if shared:
            meta[key] = made
        return made

    monkeypatch.setattr(ProxyFactory, "_request", proxy)
    return meta


class _DaemonThreads(concurrent.futures.ThreadPoolExecutor):
    """
    The loop's `to_thread` executor, on daemon threads that nothing joins, so a
    thread still waiting when the test ends never holds it up.
    """

    def submit(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        fn: Callable[..., object],
        /,
        *args: object,
        **kwargs: object,
    ) -> concurrent.futures.Future[object]:
        future: concurrent.futures.Future[object] = concurrent.futures.Future()

        def run() -> None:
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 - handed to the future
                future.set_exception(exc)

        threading.Thread(target=run, daemon=True).start()
        return future

    def shutdown(self, wait: bool = True, **kwargs: object) -> None:
        pass


def _loops(dm: str, ign: str) -> int:
    """How many decision loops of `dm` run for `ign`."""
    name = f"{dm}({ign})"
    return sum(1 for t in asyncio.all_tasks() if t.get_name() == name and not t.done())


async def _until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


async def _settled() -> None:
    """Long enough for a notification to cross a thread and a ChatReplies cycle."""
    await asyncio.sleep(1.2)


def _make(
    monkeypatch: pytest.MonkeyPatch,
    ign: str,
    metadata: dict[str, object],
    config: Path,
) -> tuple[_Bot, _Reader]:
    bot = _Bot(
        ign,
        metadata,  # pyright: ignore[reportArgumentType]
        chat_replies=False,
        discord_config=config,
    )
    reader = _Reader()
    pipe = _Pipe()
    served = serve(
        monkeypatch,
        ign,
        pipe=pipe,
        proxies=ProxyFactory(metadata),  # pyright: ignore[reportArgumentType]
        chat=reader,
    )
    bot.data = served.data
    bot.pipe = pipe  # pyright: ignore[reportAttributeAccessIssue]
    bot.barrier = threading.Barrier(1)
    return bot, reader


def _two_bots(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, object],
    tmp_path: Path,
    steps: Callable[[dict[str, tuple[_Bot, _Reader]]], Awaitable[None]],
) -> None:
    async def run() -> None:
        asyncio.get_running_loop().set_default_executor(_DaemonThreads())
        config = tmp_path / "no-discord.ini"
        bots = {
            ign: _make(monkeypatch, ign, metadata, config) for ign in ("Alice", "Bob")
        }
        started = [asyncio.create_task(bot.start()) for bot, _ in bots.values()]
        await _until(
            lambda: all(
                _loops("Training", ign) == 1 and _loops("ChatReplies", ign) == 1
                for ign in bots
            )
        )
        try:
            await steps(bots)
        finally:
            for task in asyncio.all_tasks() - {asyncio.current_task()}:
                task.cancel()
            await asyncio.gather(*started, return_exceptions=True)

    asyncio.run(run())


def test_a_gm_line_stops_only_its_own_bots_training(
    monkeypatch: pytest.MonkeyPatch, metadata: dict[str, object], tmp_path: Path
) -> None:
    async def steps(bots: dict[str, tuple[_Bot, _Reader]]) -> None:
        bots["Alice"][1].queued.append(_gm_line())
        await _until(lambda: _loops("Training", "Alice") == 0)
        await _settled()

        assert _loops("Training", "Bob") == 1
        assert _loops("ChatReplies", "Alice") == 1
        assert _loops("ChatReplies", "Bob") == 1

    _two_bots(monkeypatch, metadata, tmp_path, steps)


@pytest.mark.parametrize("order", [("Bob", "Alice"), ("Alice", "Bob")])
def test_resume_to_both_after_a_gm_runs_each_loop_once(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, object],
    tmp_path: Path,
    order: tuple[str, str],
) -> None:
    async def steps(bots: dict[str, tuple[_Bot, _Reader]]) -> None:
        bots["Alice"][1].queued.append(_gm_line())
        await _until(lambda: _loops("Training", "Alice") == 0)
        await _settled()

        for ign in order:
            bots[ign][0].resume()
        await _until(lambda: _loops("Training", "Alice") == 1)
        await _settled()

        for ign in bots:
            assert _loops("Training", ign) == 1, ign
            assert _loops("ChatReplies", ign) == 1, ign

    _two_bots(monkeypatch, metadata, tmp_path, steps)


def test_resume_to_the_gms_bot_alone_gives_back_its_training(
    monkeypatch: pytest.MonkeyPatch, metadata: dict[str, object], tmp_path: Path
) -> None:
    async def steps(bots: dict[str, tuple[_Bot, _Reader]]) -> None:
        bots["Alice"][1].queued.append(_gm_line())
        await _until(lambda: _loops("Training", "Alice") == 0)
        await _settled()

        bots["Alice"][0].resume()
        await _until(lambda: _loops("Training", "Alice") == 1)
        await _settled()

        for ign in bots:
            assert _loops("Training", ign) == 1, ign
            assert _loops("ChatReplies", ign) == 1, ign

    _two_bots(monkeypatch, metadata, tmp_path, steps)
