"""
Signals (ADR 0004), driven through a real Bot's `start`.

Nothing is faked but the edges of an Engine: the pipe to Main Process, which
records what is sent, and the clock, which the test advances. Assembly, the
SignalBoard, `BotData` and the DecisionMakers and Providers are the production
ones; the Signals, Providers and DecisionMakers are defined here, since no game
code uses a Signal yet.
"""

import asyncio
import contextlib
import functools
import threading
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

import pytest

from botting.core.bot import Bot
from botting.core.bot_data import BotData
from botting.core.data_keys import Key, Provider
from botting.core.decision_maker import DecisionMaker
from botting.core.errors import StartupRefused
from botting.core.signals import Announcement, Signal, SignalNotDeclared

IGN = "Tester"
HANDLE = 4242

PINGED: Signal[str] = Signal("pinged")
RUNG: Signal[int] = Signal("rung")
NEVER_ANNOUNCED: Signal[str] = Signal("never_announced")


class _Pipe:
    def send(self, obj: object) -> None:
        pass


class FakeClock:
    """A monotonic clock that moves only when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _sync(test: Callable[[], Coroutine[Any, Any, None]]) -> Callable[[], None]:
    """Run an async test on its own event loop, as `test_data_keys.py` does."""

    @functools.wraps(test)
    def run() -> None:
        asyncio.run(asyncio.wait_for(test(), timeout=10))

    return run


# --- the DecisionMakers and the Provider --------------------------------------------


class Idle(DecisionMaker):
    async def _decide(self) -> None:
        await asyncio.Event().wait()


class Announcer(Idle):
    announces = (PINGED,)


class Waiter(Idle):
    awaits = (PINGED,)


class OtherWaiter(Idle):
    awaits = (PINGED,)


class Stranger(Idle):
    """Declares nothing."""


class HopefulWaiter(Idle):
    awaits = (NEVER_ANNOUNCED,)


class Bell(Provider):
    announces = (RUNG,)

    def setup(self) -> None:
        self.register(CHIME, lambda: 0)


CHIME: Key[int] = Key("chime", provider=Bell)


class BellListener(Idle):
    reads = (CHIME,)
    awaits = (RUNG,)


class BellAnnouncerInSetup(Provider):
    """Announces while it is set up, as a Provider that learns something may."""

    announces = (RUNG,)

    def setup(self) -> None:
        self.announce(RUNG, 7)
        self.register(SETUP_CHIME, lambda: 0)


SETUP_CHIME: Key[int] = Key("setup_chime", provider=BellAnnouncerInSetup)


class SetupListener(Idle):
    reads = (SETUP_CHIME,)
    awaits = (RUNG,)

    def setup(self) -> None:
        self.heard = self.last(RUNG)


# --- the Bot ------------------------------------------------------------------------


class _TestBot(Bot):
    def __init__(self, *classes: type[DecisionMaker]) -> None:
        super().__init__(IGN, {})  # pyright: ignore[reportArgumentType] - no Manager needed
        self.classes = list(classes)

    def find_handle(self) -> int:
        return HANDLE

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return self.classes


def _prepared(bot: _TestBot, clock: FakeClock | None = None) -> None:
    """What `Bot.child_init` gives a Bot inside the Engine, minus the process."""
    bot.data = BotData(IGN, clock=clock) if clock else BotData(IGN)
    bot.data.set_static("handle", HANDLE)
    bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue] - records instead of sending
    bot.barrier = threading.Barrier(1)


@contextlib.asynccontextmanager
async def _started(
    *classes: type[DecisionMaker], clock: FakeClock | None = None
) -> AsyncIterator[_TestBot]:
    """A Bot started as an Engine starts it, minus the process around it."""
    bot = _TestBot(*classes)
    _prepared(bot, clock)
    run = asyncio.create_task(bot.start())
    while bot.supervisor is None and not run.done():
        await asyncio.sleep(0)
    if run.done():
        run.result()
    try:
        yield bot
    finally:
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run


def _dm[T: DecisionMaker](bot: Bot, cls: type[T]) -> T:
    [dm] = [dm for dm in bot.decision_makers if type(dm) is cls]
    assert isinstance(dm, cls)
    return dm


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


# --- announcing and waiting ---------------------------------------------------------


@_sync
async def test_wait_for_returns_the_payload_of_the_next_announcement() -> None:
    async with _started(Announcer, Waiter) as bot:
        announcer, waiter = _dm(bot, Announcer), _dm(bot, Waiter)

        waiting = asyncio.create_task(waiter.wait_for(PINGED))
        await _settle()
        assert not waiting.done()

        announcer.announce(PINGED, "hello")

        assert await asyncio.wait_for(waiting, timeout=1) == "hello"


@_sync
async def test_every_waiter_wakes_on_one_announcement() -> None:
    async with _started(Announcer, Waiter, OtherWaiter) as bot:
        announcer = _dm(bot, Announcer)
        waiting = [
            asyncio.create_task(_dm(bot, Waiter).wait_for(PINGED)),
            asyncio.create_task(_dm(bot, Waiter).wait_for(PINGED)),
            asyncio.create_task(_dm(bot, OtherWaiter).wait_for(PINGED)),
        ]
        await _settle()

        announcer.announce(PINGED, "all of you")

        results = await asyncio.wait_for(asyncio.gather(*waiting), timeout=1)
        assert results == ["all of you"] * 3


@_sync
async def test_wait_for_ignores_an_announcement_made_before_the_call() -> None:
    async with _started(Announcer, Waiter) as bot:
        announcer, waiter = _dm(bot, Announcer), _dm(bot, Waiter)
        announcer.announce(PINGED, "old")

        waiting = asyncio.create_task(waiter.wait_for(PINGED))
        await _settle()
        assert not waiting.done()

        announcer.announce(PINGED, "new")

        assert await asyncio.wait_for(waiting, timeout=1) == "new"


@_sync
async def test_a_cancelled_wait_does_not_stay_on_the_board() -> None:
    async with _started(Announcer, Waiter) as bot:
        announcer, waiter = _dm(bot, Announcer), _dm(bot, Waiter)
        cancelled = asyncio.create_task(waiter.wait_for(PINGED))
        await _settle()
        cancelled.cancel()
        await _settle()
        waiting = asyncio.create_task(waiter.wait_for(PINGED))
        await _settle()

        announcer.announce(PINGED, "still works")

        assert await asyncio.wait_for(waiting, timeout=1) == "still works"
        assert cancelled.cancelled()


@_sync
async def test_a_provider_announces_to_a_decision_maker_awaiting() -> None:
    async with _started(BellListener) as bot:
        listener = _dm(bot, BellListener)
        [bell] = bot.providers
        assert isinstance(bell, Bell)
        waiting = asyncio.create_task(listener.wait_for(RUNG))
        await _settle()

        bell.announce(RUNG, 3)

        assert await asyncio.wait_for(waiting, timeout=1) == 3


# --- last ---------------------------------------------------------------------------


@_sync
async def test_last_is_none_until_announced_then_the_latest_payload_and_when() -> None:
    clock = FakeClock()
    async with _started(Announcer, Waiter, clock=clock) as bot:
        announcer, waiter = _dm(bot, Announcer), _dm(bot, Waiter)
        assert waiter.last(PINGED) is None
        assert announcer.last(PINGED) is None

        announcer.announce(PINGED, "first")
        clock.advance(5)
        announcer.announce(PINGED, "second")

        assert waiter.last(PINGED) == Announcement("second", 1005.0)
        assert announcer.last(PINGED) == Announcement("second", 1005.0)


@_sync
async def test_a_provider_announced_in_setup_is_there_for_a_decision_maker_setup() -> (
    None
):
    async with _started(SetupListener) as bot:
        heard = _dm(bot, SetupListener).heard

    assert heard is not None
    assert heard.payload == 7


# --- what is refused ----------------------------------------------------------------


@_sync
async def test_announcing_an_undeclared_signal_raises() -> None:
    async with _started(Announcer, Stranger) as bot:
        with pytest.raises(SignalNotDeclared, match="'pinged'"):
            _dm(bot, Stranger).announce(PINGED, "nobody declared me")
        with pytest.raises(SignalNotDeclared, match="'rung'"):
            _dm(bot, Announcer).announce(RUNG, 1)  # pyright: ignore[reportArgumentType] - undeclared on purpose


@_sync
async def test_a_provider_announcing_an_undeclared_signal_raises() -> None:
    async with _started(BellListener) as bot:
        [bell] = bot.providers
        with pytest.raises(SignalNotDeclared, match="'pinged'"):
            bell.announce(PINGED, "not mine")


@_sync
async def test_waiting_for_or_asking_for_an_undeclared_signal_raises() -> None:
    async with _started(Announcer, Stranger) as bot:
        stranger = _dm(bot, Stranger)
        with pytest.raises(SignalNotDeclared, match="'pinged'"):
            await stranger.wait_for(PINGED)
        with pytest.raises(SignalNotDeclared, match="'pinged'"):
            stranger.last(PINGED)
        # Announcing is not awaiting: the announcer may not wait for its own.
        with pytest.raises(SignalNotDeclared, match="'pinged'"):
            await _dm(bot, Announcer).wait_for(PINGED)


def _refused(*classes: type[DecisionMaker]) -> StartupRefused:
    bot = _TestBot(*classes)
    _prepared(bot)
    with pytest.raises(StartupRefused) as refused:
        asyncio.run(asyncio.wait_for(bot.start(), timeout=5))
    return refused.value


def test_awaiting_a_signal_nothing_announces_is_refused_naming_it() -> None:
    refused = _refused(Announcer, HopefulWaiter)

    assert "HopefulWaiter" in str(refused)
    assert "'never_announced'" in str(refused)


def test_a_signal_announced_by_a_provider_the_bot_builds_is_not_refused() -> None:
    async def start() -> None:
        async with _started(BellListener):
            pass

    asyncio.run(start())


def test_a_signal_only_a_provider_nobody_reads_announces_is_refused() -> None:
    """A Provider no DecisionMaker reads is not built, so it announces nothing."""

    class Deaf(Idle):
        awaits = (RUNG,)

    refused = _refused(Deaf)

    assert "'rung'" in str(refused)


def test_nothing_is_built_when_a_signal_is_refused() -> None:
    built: list[str] = []

    class Careful(HopefulWaiter):
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
            built.append("built")
            super().__init__(*args, **kwargs)

    _refused(Careful)

    assert built == []
