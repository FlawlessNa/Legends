"""
A GM line stops the training of the bot it was read on, and no other (#489).

Two Bots in one session, each a training loop and the real `ChatReplies`, with
the real enabler and disabler threads on the real Bot lifecycle. The Main
Process proxies are in-process primitives in one metadata dict, which every
Bot shares as Engines share the Manager's: a key already made is handed back,
not made again. The chat is scripted, and replying is off, so no model is
asked; the GM stop runs with replies off as with them on.

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

from botting.core import Bot, BotData, DecisionMaker, ProxyFactory
from botting.screen import Reading
from maple.decision_makers.chat_replies import ChatReplies
from maple.screen.chat import ChatKind, ChatLine


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
    The loop's `to_thread` executor, on daemon threads that nothing joins: the
    enabler and disabler threads wait on their Conditions for as long as the
    process lives, which in an Engine is how they end.
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


def _make(ign: str, metadata: dict[str, object], config: Path) -> tuple[_Bot, _Reader]:
    bot = _Bot(
        ign,
        metadata,  # pyright: ignore[reportArgumentType]
        chat_replies=False,
        discord_config=config,
    )
    reader = _Reader()
    data = BotData(ign)
    data.set_static("handle", 1)
    data.set_static("replies_on", True)
    data.set_static(
        "decision_maker_names",
        tuple(c.__name__ for c in bot._decision_makers()),  # pyright: ignore[reportPrivateUsage]
    )
    data.set_static("chat_reader", reader)
    data.create_attribute("current_frame", lambda: None)
    bot.data = data
    bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue]
    bot.barrier = threading.Barrier(1)
    return bot, reader


def _two_bots(
    metadata: dict[str, object],
    tmp_path: Path,
    steps: Callable[[dict[str, tuple[_Bot, _Reader]]], Awaitable[None]],
) -> None:
    async def run() -> None:
        asyncio.get_running_loop().set_default_executor(_DaemonThreads())
        config = tmp_path / "no-discord.ini"
        bots = {ign: _make(ign, metadata, config) for ign in ("Alice", "Bob")}
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
    metadata: dict[str, object], tmp_path: Path
) -> None:
    async def steps(bots: dict[str, tuple[_Bot, _Reader]]) -> None:
        bots["Alice"][1].queued.append(_gm_line())
        await _until(lambda: _loops("Training", "Alice") == 0)
        await _settled()

        assert _loops("Training", "Bob") == 1
        assert _loops("ChatReplies", "Alice") == 1
        assert _loops("ChatReplies", "Bob") == 1

    _two_bots(metadata, tmp_path, steps)


@pytest.mark.parametrize("order", [("Bob", "Alice"), ("Alice", "Bob")])
def test_resume_to_both_after_a_gm_runs_each_loop_once(
    metadata: dict[str, object], tmp_path: Path, order: tuple[str, str]
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

    _two_bots(metadata, tmp_path, steps)


def test_resume_to_the_gms_bot_alone_gives_back_its_training(
    metadata: dict[str, object], tmp_path: Path
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

    _two_bots(metadata, tmp_path, steps)
