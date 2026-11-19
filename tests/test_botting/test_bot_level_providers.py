"""
Bot-level Providers, `Providers`, and what DecisionMakers ask of them (ADR
0004), driven through a real Bot's `child_init` and `start`.

A Bot-level Provider serves what its Bot found at start: the Bot builds it in
`child_init` (`Providers.add`), and assembly builds only the Providers the
DecisionMakers read that are not built yet. Code outside assembly, such as a
test, builds one on demand (`Providers.ensure`).

The Providers and DecisionMakers are `test_data_keys.py`'s, plus a Bot-level one.
"""

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator
from typing import Any

import pytest

from botting.core import HANDLE, REPLIES_ON, RepliesProvider, WindowProvider
from botting.core.bot_data import BotData
from botting.core.data_keys import Key, KeyNotDeclared, Provider, Providers
from botting.core.errors import StartupRefused
from botting.core.proxy_factory import ProxyFactory
from tests.test_botting.test_data_keys import (
    COUNT,
    DOUBLE,
    IGN,
    LOG,
    Counter,
    CountReader,
    Doubler,
    Idle,
    Logged,
    _dm,  # pyright: ignore[reportPrivateUsage]
    _fresh_log,  # noqa: F401 - the fixture  # pyright: ignore[reportPrivateUsage]
    _Pipe,  # pyright: ignore[reportPrivateUsage]
    _TestBot,  # pyright: ignore[reportPrivateUsage]
)

FOUND_AT_START = "found at start"


class Found(Logged):
    """A Bot-level Provider: serves FOUND, what its Bot found at start."""

    bot_level = True

    def __init__(self, *args: Any, found: str, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        self.found = found

    def setup(self) -> None:
        super().setup()
        self.register(FOUND, lambda: self.found)


FOUND: Key[str] = Key("found", provider=Found)


class FoundReader(Idle):
    reads = (FOUND,)


class OtherFoundReader(Idle):
    reads = (FOUND,)


class _FindingBot(_TestBot):
    """A Bot that builds `Found` in `child_init`, as a game layer does."""

    def child_init(self, pipe: Any, barrier: Any) -> None:  # noqa: ANN401 - the Engine's
        super().child_init(pipe, barrier)
        assert self.data is not None
        assert self.data.providers is not None
        self.data.providers.add(Found, found=FOUND_AT_START)


@contextlib.asynccontextmanager
async def _started(bot: _TestBot) -> AsyncIterator[_TestBot]:
    """`bot` started as an Engine starts it: `child_init`, then `start`."""
    bot.child_init(_Pipe(), threading.Barrier(1))  # pyright: ignore[reportArgumentType] - records instead of sending
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


def _providers(data: BotData) -> Providers:
    return Providers(data, _Pipe(), ProxyFactory({}), {})  # pyright: ignore[reportArgumentType] - records instead of sending


# --- what a Bot builds ---------------------------------------------------------------


def test_child_init_serves_the_handle_find_handle_found_and_the_replies_switch() -> (
    None
):
    bot = _TestBot()
    bot.child_init(_Pipe(), None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.read(HANDLE) == 4242
    assert bot.data.handle == 4242
    assert bot.data.read(REPLIES_ON) is True
    assert [type(p) for p in bot.providers] == [WindowProvider, RepliesProvider]


def test_a_bot_level_provider_is_set_up_in_child_init_and_never_rebuilt() -> None:
    async def scenario() -> None:
        async with _started(_FindingBot(FoundReader, OtherFoundReader)) as bot:
            assert _dm(bot, FoundReader).read(FOUND) == FOUND_AT_START
            assert [type(p) for p in bot.providers] == [
                WindowProvider,
                RepliesProvider,
                Found,
            ]
            assert LOG == [
                ("built", "Found"),
                ("setup", "Found"),
                ("built", "FoundReader"),
                ("built", "OtherFoundReader"),
                ("setup", "FoundReader"),
                ("setup", "OtherFoundReader"),
            ]

    asyncio.run(scenario())


def test_reading_a_bot_level_key_the_bot_does_not_build_is_refused_naming_it() -> None:
    """Before any Provider assembly would build is: no I/O has started."""
    bot = _TestBot(CountReader, FoundReader)
    bot.child_init(_Pipe(), threading.Barrier(1))  # pyright: ignore[reportArgumentType]

    with pytest.raises(StartupRefused, match=r"Found is Bot-level, and Tester's Bot"):
        asyncio.run(bot.start())
    assert LOG == []


def test_only_a_bot_level_provider_is_added_once_after_what_it_needs() -> None:
    providers = _providers(BotData(IGN))

    with pytest.raises(ValueError, match="Counter is not Bot-level"):
        providers.add(Counter)
    providers.add(Found, found=FOUND_AT_START)
    with pytest.raises(ValueError, match="Found is built already"):
        providers.add(Found, found=FOUND_AT_START)

    class NeedsCount(Provider):
        bot_level = True
        needs = (COUNT,)

    with pytest.raises(ValueError, match="needs Counter, which is not built yet"):
        providers.add(NeedsCount)


def test_an_added_value_wins_over_a_profile_setting_of_its_name() -> None:
    data = BotData(IGN)
    providers = Providers(data, _Pipe(), ProxyFactory({}), {"found": "setting"})  # pyright: ignore[reportArgumentType]

    providers.add(Found, found=FOUND_AT_START)

    assert data.read(FOUND) == FOUND_AT_START


# --- building on demand ---------------------------------------------------------------


def test_ensure_builds_it_once_after_what_it_needs() -> None:
    data = BotData(IGN)
    providers = _providers(data)

    providers.ensure(Doubler)
    providers.ensure(Doubler)
    providers.ensure(Counter)

    assert LOG == [
        ("built", "Counter"),
        ("built", "Doubler"),
        ("setup", "Counter"),
        ("setup", "Doubler"),
    ]
    assert data.read(DOUBLE) == 2


# --- refreshing ----------------------------------------------------------------------


def test_refresh_reads_now_whatever_the_threshold() -> None:
    """COUNT refreshes every second; the test reads it within one."""

    async def scenario() -> None:
        async with _started(_TestBot(CountReader, Idle)) as bot:
            reader = _dm(bot, CountReader)
            assert reader.read(COUNT) == 1
            assert reader.refresh(COUNT) == 2
            assert reader.read(COUNT) == 2
            with pytest.raises(
                KeyNotDeclared, match=r"Idle\(Tester\) refreshed 'count'"
            ):
                _dm(bot, Idle).refresh(COUNT)

    asyncio.run(scenario())


def test_a_provider_reads_and_refreshes_its_own_keys() -> None:
    data = BotData(IGN)
    providers = _providers(data)
    providers.ensure(Counter)
    [counter] = list(providers)

    assert counter.read(COUNT) == 1
    assert counter.refresh(COUNT) == 2


def test_refresh_of_a_key_nothing_provides_raises() -> None:
    with pytest.raises(LookupError, match="'count'"):
        BotData(IGN).refresh(COUNT)
