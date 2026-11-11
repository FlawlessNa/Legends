"""
`Bot.resume()` on real DecisionMakers inside a real TaskGroup, with the Main
Process proxies stubbed by in-process primitives.

RESUME restarts what PAUSE stopped, as it always has; it leaves a running loop
alone, so a RESUME with no PAUSE never runs one twice; and a DecisionMaker's
`on_resume` hook gives back what it disabled, through its enablers.
"""

import asyncio
import concurrent.futures
import queue
import threading
from collections.abc import Callable
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
    """Gives `Training` back on RESUME, as `ChatReplies` does after a GM."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        self.disabled: tuple[str, ...] = ()

    def on_resume(self) -> tuple[str, ...]:
        given_back, self.disabled = self.disabled, ()
        self._enable_decision_makers(*given_back)
        return given_back


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


def _loops(name: str) -> list[asyncio.Task]:
    return [
        t
        for t in asyncio.all_tasks()
        if t.get_name().startswith(name)
        and not t.done()
        and "abler" not in t.get_name()
    ]


async def _until(predicate: Any, timeout: float = 2.0) -> None:  # noqa: ANN401
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


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


def _scenario(metadata: dict[str, object], steps: Any) -> None:  # noqa: ANN401
    async def run() -> None:
        asyncio.get_running_loop().set_default_executor(_DaemonThreads())
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


def test_what_a_decision_maker_disabled_comes_back_through_its_hook_once(
    metadata: dict[str, object],
) -> None:
    async def steps(bot: _Bot) -> None:
        chat = next(dm for dm in bot.decision_makers if isinstance(dm, Chat))
        training = next(dm for dm in bot.decision_makers if isinstance(dm, Training))
        chat._disable_decision_makers("Training")  # pyright: ignore[reportPrivateUsage]
        chat.disabled = ("Training",)
        await _until(lambda: not _loops("Training"))

        bot.resume()
        await _until(lambda: len(_loops("Training")) == 1)
        await asyncio.sleep(0.1)

        assert len(_loops("Training")) == 1
        assert len(_loops("Chat")) == 1
        # Given back as enabled, so the next disable stops it again.
        assert training._enabled  # pyright: ignore[reportPrivateUsage]

    _scenario(metadata, steps)


def test_an_enable_after_resume_restarted_a_disabled_loop_runs_no_loop_twice(
    metadata: dict[str, object],
) -> None:
    """A loop disabled by someone whose hook doesn't give it back is restarted by
    RESUME, as PAUSE leaves it; a later enable then finds it running (#489)."""

    async def steps(bot: _Bot) -> None:
        chat = next(dm for dm in bot.decision_makers if isinstance(dm, Chat))
        training = next(dm for dm in bot.decision_makers if isinstance(dm, Training))
        chat._disable_decision_makers("Training")  # pyright: ignore[reportPrivateUsage]
        await _until(lambda: not _loops("Training"))

        bot.resume()
        await _until(lambda: len(_loops("Training")) == 1)
        assert training._enabled  # pyright: ignore[reportPrivateUsage]

        chat._enable_decision_makers("Training")  # pyright: ignore[reportPrivateUsage]
        await asyncio.sleep(0.1)

        assert len(_loops("Training")) == 1

    _scenario(metadata, steps)


class _Pipe:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, item: object) -> None:
        self.sent.append(item)
