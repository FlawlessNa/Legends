"""
`Bot.resume()` on real DecisionMakers inside a real TaskGroup, with the Main
Process proxies stubbed by in-process primitives.

RESUME restarts what PAUSE stopped, as it always has; it leaves a running loop
alone, so a RESUME with no PAUSE never runs one twice; and it ends the legacy
shim's Pauses without a later enable running a loop twice.
"""

import asyncio
import queue
import threading
from typing import Any

import pytest

from botting.core import Bot, BotData, DecisionMaker, ProxyFactory


class _Loop(DecisionMaker):
    _throttle = 0.01

    async def _decide(self) -> None:
        pass


class Training(_Loop):
    pass


class Chat(_Loop):
    """Disables `Training` through the legacy shim."""


class _Bot(Bot):
    def find_handle(self) -> int:
        return 1

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [Training, Chat]


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
        kind = (
            queue.Queue
            if primitive_type == "Queue"
            else getattr(threading, primitive_type)
        )
        made = kind(*args, **kwargs)
        meta[key] = made
        return made

    monkeypatch.setattr(ProxyFactory, "_request", proxy)
    return meta


def _loops(dm: str) -> list[asyncio.Task]:
    """The decision loops of `dm` running for Alice: not its Supervisor task."""
    name = f"{dm}(Alice)"
    return [t for t in asyncio.all_tasks() if t.get_name() == name and not t.done()]


async def _until(predicate: Any, timeout: float = 2.0) -> None:  # noqa: ANN401
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


def _scenario(metadata: dict[str, object], steps: Any) -> None:  # noqa: ANN401
    async def run() -> None:
        bot = _Bot("Alice", metadata)  # pyright: ignore[reportArgumentType]
        bot.data = BotData("Alice")
        bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue]
        bot.barrier = threading.Barrier(1)
        started = asyncio.create_task(bot.start())
        await _until(lambda: len(_loops("Training")) == 1 and len(_loops("Chat")) == 1)
        try:
            await steps(bot)
        finally:
            for task in asyncio.all_tasks() - {asyncio.current_task()}:
                task.cancel()
            await asyncio.gather(started, return_exceptions=True)

    asyncio.run(run())


def test_a_resume_with_no_pause_runs_no_loop_twice(metadata: dict[str, object]) -> None:
    async def steps(bot: _Bot) -> None:
        bot.resume()
        await asyncio.sleep(0.05)
        assert len(_loops("Training")) == 1
        assert len(_loops("Chat")) == 1

    _scenario(metadata, steps)


def test_pause_then_resume_restarts_every_loop(metadata: dict[str, object]) -> None:
    async def steps(bot: _Bot) -> None:
        bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue]
        bot.data.set_static("handle", 1)  # pyright: ignore[reportOptionalMemberAccess]
        bot.pause()
        await _until(lambda: not _loops("Training") and not _loops("Chat"))
        bot.resume()
        await _until(lambda: len(_loops("Training")) == 1 and len(_loops("Chat")) == 1)

    _scenario(metadata, steps)


def test_an_enable_after_resume_restarted_a_disabled_loop_runs_no_loop_twice(
    metadata: dict[str, object],
) -> None:
    """A loop disabled through the shim is restarted by RESUME, as PAUSE leaves
    it; a later enable then finds it running (#489)."""

    async def steps(bot: _Bot) -> None:
        chat = next(dm for dm in bot.decision_makers if isinstance(dm, Chat))
        chat._disable_decision_makers("Training")  # pyright: ignore[reportPrivateUsage]
        await _until(lambda: not _loops("Training"))

        bot.resume()
        await _until(lambda: len(_loops("Training")) == 1)

        chat._enable_decision_makers("Training")  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(0.1)

        assert len(_loops("Training")) == 1

    _scenario(metadata, steps)


class _Pipe:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, item: object) -> None:
        self.sent.append(item)
