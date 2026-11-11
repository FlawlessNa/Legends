"""
Data Keys, Providers and assembly (ADR 0004), driven through a real Bot's `start`.

Nothing here is faked but the edges of an Engine: the pipe to Main Process, which
records what is sent, and the clock, which the test advances. Assembly, the
Providers, `BotData` and the DecisionMakers are the production ones; the Providers
and DecisionMakers are defined here, since no game Provider exists yet.

Every Provider and DecisionMaker below appends to `LOG` when it is built and when
it is set up, so a test reads what assembly did, and in which order.
"""

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest

from botting.core.action_data import ActionRequest
from botting.core.bot import Bot
from botting.core.bot_data import BotData, OwnedByProvider
from botting.core.data_keys import Key, KeyNotDeclared, Provider
from botting.core.decision_maker import DecisionMaker
from botting.core.errors import StartupRefused

IGN = "Tester"
HANDLE = 4242

#: What was built and set up, in order: ("built" | "setup", class name).
LOG: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def _fresh_log() -> Iterator[None]:
    LOG.clear()
    yield
    LOG.clear()


class _Pipe:
    """The Engine's end of the pipe to Main Process: records what is sent."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, obj: object) -> None:
        self.sent.append(obj)


class FakeClock:
    """A monotonic clock that moves only when the test says so."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- the Providers ------------------------------------------------------------------


class Logged(Provider):
    """A Provider that logs when it is built and set up."""

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        LOG.append(("built", type(self).__name__))

    def setup(self) -> None:
        LOG.append(("setup", type(self).__name__))


class Counter(Logged):
    """Provides COUNT, which goes up by one at every refresh, every second."""

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        self.updates = 0

    def setup(self) -> None:
        super().setup()
        self.register(COUNT, self._next, threshold=1.0)

    def _next(self) -> int:
        self.updates += 1
        return self.updates


COUNT: Key[int] = Key("count", provider=Counter, legacy_name="legacy_count")


class Doubler(Logged):
    """Needs COUNT, and provides twice its value at setup."""

    needs = (COUNT,)

    def setup(self) -> None:
        super().setup()
        self.seen = self.read(COUNT)
        self.register(DOUBLE, lambda: 2 * self.read(COUNT))


DOUBLE: Key[int] = Key("double", provider=Doubler)


class Configured(Logged):
    """Provides the profile setting it was built with."""

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        mob_count_threshold: int = 0,
        **settings: object,
    ) -> None:
        super().__init__(*args, **settings)
        self.mob_count_threshold = mob_count_threshold

    def setup(self) -> None:
        super().setup()
        self.register(THRESHOLD, lambda: self.mob_count_threshold)


THRESHOLD: Key[int] = Key("threshold", provider=Configured)


class Forgetful(Logged):
    """Provides a key, and forgets to register it."""


FORGOTTEN: Key[int] = Key("forgotten", provider=Forgetful)


class Unbuildable(Provider):
    """Must never be built: assembly refuses before it gets to it."""

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        raise AssertionError(f"{type(self).__name__} was built")


class Ouro(Unbuildable):
    pass


class Boros(Unbuildable):
    pass


OURO: Key[int] = Key("ouro", provider=Ouro)
BOROS: Key[int] = Key("boros", provider=Boros)
Ouro.needs = (BOROS,)
Boros.needs = (OURO,)


class TwinA(Unbuildable):
    pass


class TwinB(Unbuildable):
    pass


TWIN_A: Key[int] = Key("twin", provider=TwinA)
TWIN_B: Key[int] = Key("twin", provider=TwinB)
#: Its legacy name is another key's name.
SHADOW: Key[int] = Key("shadow", provider=TwinB, legacy_name="count")


# --- the DecisionMakers -------------------------------------------------------------


class Idle(DecisionMaker):
    """Logs its build and setup, then never decides twice."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        LOG.append(("built", type(self).__name__))

    def setup(self) -> None:
        LOG.append(("setup", type(self).__name__))

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class CountReader(Idle):
    reads = (COUNT,)


class OtherCountReader(Idle):
    reads = (COUNT,)


class CountObserver(Idle):
    observes = (COUNT,)


class DoubleReader(Idle):
    reads = (DOUBLE,)


class ThresholdReader(Idle):
    reads = (THRESHOLD,)


class ForgottenReader(Idle):
    reads = (FORGOTTEN,)


class Unported(DecisionMaker):
    """Declares nothing, and reads COUNT by its legacy name, as a mixin user does."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        self.seen: list[int] = []

    async def _decide(self) -> None:
        self.seen.append(self.data.legacy_count)
        await asyncio.Event().wait()


class NeverBuilt(DecisionMaker):
    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        raise AssertionError(f"{type(self).__name__} was built")

    async def _decide(self) -> None:
        raise AssertionError("never runs")


class CycleReader(NeverBuilt):
    reads = (OURO,)


class TwinReader(NeverBuilt):
    reads = (TWIN_A, TWIN_B)


class ShadowReader(NeverBuilt):
    reads = (SHADOW,)


# --- the Bot ------------------------------------------------------------------------


class _TestBot(Bot):
    def __init__(self, *classes: type[DecisionMaker], **settings: object) -> None:
        super().__init__(IGN, {}, **settings)  # pyright: ignore[reportArgumentType] - no Manager needed
        self.classes = list(classes)

    def find_handle(self) -> int:
        return HANDLE

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return self.classes


def _prepared(bot: _TestBot, clock: FakeClock | None = None) -> _Pipe:
    """What `Bot.child_init` gives a Bot inside the Engine, minus the process."""
    pipe = _Pipe()
    bot.data = BotData(IGN, clock=clock) if clock else BotData(IGN)
    bot.data.set_static("handle", HANDLE)
    bot.pipe = pipe  # pyright: ignore[reportAttributeAccessIssue] - records instead of sending
    bot.barrier = threading.Barrier(1)
    return pipe


@contextlib.asynccontextmanager
async def _started(
    *classes: type[DecisionMaker], clock: FakeClock | None = None, **settings: object
) -> AsyncIterator[_TestBot]:
    """A Bot started as an Engine starts it, minus the process around it."""
    bot = _TestBot(*classes, **settings)
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


def _refused(*classes: type[DecisionMaker]) -> StartupRefused:
    """The refusal of a Bot running `classes`. A Bot that starts instead fails."""
    bot = _TestBot(*classes)
    _prepared(bot)
    with pytest.raises(StartupRefused) as refused:
        asyncio.run(asyncio.wait_for(bot.start(), timeout=5))
    return refused.value


# --- assembly refuses a Bot wired wrong ---------------------------------------------


def test_a_cycle_between_providers_is_refused_naming_it_before_anything_is_built() -> (
    None
):
    refused = _refused(Idle, CycleReader)

    assert str(refused) == (
        "Providers form a cycle: Ouro needs 'boros' from Boros, "
        "which needs 'ouro' from Ouro."
    )
    assert LOG == []


def test_two_keys_with_the_same_name_are_refused_naming_both() -> None:
    refused = _refused(Idle, TwinReader)

    assert "'twin'" in str(refused)
    assert "TwinA" in str(refused)
    assert "TwinB" in str(refused)
    assert LOG == []


def test_a_legacy_name_that_is_another_keys_name_is_refused() -> None:
    refused = _refused(CountReader, ShadowReader)

    assert "'count'" in str(refused)
    assert "Counter" in str(refused)
    assert "TwinB" in str(refused)
    assert LOG == []


def test_a_provider_that_does_not_register_a_key_it_provides_is_refused() -> None:
    refused = _refused(ForgottenReader)

    assert "Forgetful" in str(refused)
    assert "'forgotten'" in str(refused)
    assert ("built", "ForgottenReader") not in LOG


# --- assembly builds what is read, once -----------------------------------------------


def test_two_readers_of_one_key_build_and_set_up_its_provider_once() -> None:
    async def scenario() -> None:
        async with _started(CountReader, OtherCountReader) as bot:
            assert LOG.count(("built", "Counter")) == 1
            assert LOG.count(("setup", "Counter")) == 1
            assert [type(p) for p in bot.providers] == [Counter]
            assert _dm(bot, CountReader).read(COUNT) == 1
            assert _dm(bot, OtherCountReader).read(COUNT) == 1

    asyncio.run(scenario())


def test_a_key_that_is_only_observed_builds_nothing() -> None:
    async def scenario() -> None:
        async with _started(CountObserver) as bot:
            assert ("built", "Counter") not in LOG
            assert bot.providers == []
            assert _dm(bot, CountObserver).peek(COUNT) is None

    asyncio.run(scenario())


def test_providers_are_set_up_before_their_dependents_and_decision_makers_last() -> (
    None
):
    async def scenario() -> None:
        async with _started(DoubleReader, Idle) as bot:
            assert LOG == [
                ("built", "Counter"),
                ("built", "Doubler"),
                ("setup", "Counter"),
                ("setup", "Doubler"),
                ("built", "DoubleReader"),
                ("built", "Idle"),
                ("setup", "DoubleReader"),
                ("setup", "Idle"),
            ]
            doubler = bot.providers[1]
            assert isinstance(doubler, Doubler)
            assert doubler.seen == 1
            assert _dm(bot, DoubleReader).read(DOUBLE) == 2

    asyncio.run(scenario())


def test_a_provider_is_built_with_the_bots_profile_settings() -> None:
    async def scenario() -> None:
        async with _started(ThresholdReader, mob_count_threshold=7) as bot:
            assert _dm(bot, ThresholdReader).read(THRESHOLD) == 7

    asyncio.run(scenario())


def test_a_bot_that_declares_nothing_builds_no_provider_and_runs() -> None:
    async def scenario() -> None:
        async with _started(Unported) as bot:
            assert bot.providers == []
            assert LOG == []

    asyncio.run(scenario())


# --- reading and peeking --------------------------------------------------------------


def test_reading_refreshes_on_the_keys_threshold() -> None:
    clock = FakeClock()

    async def scenario() -> None:
        async with _started(CountReader, clock=clock) as bot:
            reader = _dm(bot, CountReader)
            assert reader.read(COUNT) == 1
            clock.advance(0.5)
            assert reader.read(COUNT) == 1
            clock.advance(0.6)
            assert reader.read(COUNT) == 2

    asyncio.run(scenario())


def test_peek_returns_the_last_known_value_without_refreshing() -> None:
    clock = FakeClock()

    async def scenario() -> None:
        async with _started(CountReader, CountObserver, clock=clock) as bot:
            assert _dm(bot, CountReader).read(COUNT) == 1
            clock.advance(5)
            assert _dm(bot, CountObserver).peek(COUNT) == 1
            assert _dm(bot, CountReader).peek(COUNT) == 1
            counter = bot.providers[0]
            assert isinstance(counter, Counter)
            assert counter.updates == 1

    asyncio.run(scenario())


def test_reading_or_peeking_an_undeclared_key_raises() -> None:
    async def scenario() -> None:
        async with _started(CountReader, CountObserver, Idle) as bot:
            with pytest.raises(KeyNotDeclared, match=r"Idle.*'count'"):
                _dm(bot, Idle).read(COUNT)
            with pytest.raises(KeyNotDeclared, match=r"Idle.*'count'"):
                _dm(bot, Idle).peek(COUNT)
            with pytest.raises(KeyNotDeclared, match=r"CountObserver.*'count'"):
                _dm(bot, CountObserver).read(COUNT)

    asyncio.run(scenario())


def test_a_provider_reading_a_key_it_does_not_need_raises() -> None:
    async def scenario() -> None:
        async with _started(DoubleReader) as bot:
            counter = bot.providers[0]
            with pytest.raises(KeyNotDeclared, match=r"Counter.*'double'"):
                counter.read(DOUBLE)

    asyncio.run(scenario())


def test_a_provider_error_handler_retries_the_update_as_today() -> None:
    handled: list[str] = []
    attempts: list[int] = []

    class Flaky(Provider):
        def setup(self) -> None:
            self.register(FLAKY, self._read, error_handler=lambda: handled.append("h"))

        def _read(self) -> str:
            attempts.append(1)
            if len(attempts) == 1:
                raise ValueError("first read fails")
            return "ok"

    FLAKY: Key[str] = Key("flaky", provider=Flaky)

    class FlakyReader(Idle):
        reads = (FLAKY,)

    async def scenario() -> None:
        async with _started(FlakyReader) as bot:
            assert _dm(bot, FlakyReader).read(FLAKY) == "ok"
            assert handled == ["h"]
            assert len(attempts) == 2

    asyncio.run(scenario())


# --- the legacy bridge ----------------------------------------------------------------


def test_an_unported_decision_maker_reads_a_provided_value_by_its_legacy_name() -> None:
    async def scenario() -> None:
        async with _started(CountReader, Unported) as bot:
            unported = _dm(bot, Unported)
            for _ in range(20):
                if unported.seen:
                    break
                await asyncio.sleep(0.01)
            assert unported.seen == [1]
            assert bot.data is not None
            assert bot.data.get_last_known_value("legacy_count", update=False) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("name", ["legacy_count", "count"])
def test_creating_an_attribute_a_provider_owns_raises(name: str) -> None:
    async def scenario() -> None:
        async with _started(CountReader) as bot:
            data = bot.data
            assert data is not None
            with pytest.raises(OwnedByProvider, match=r"Counter"):
                data.create_attribute(name, lambda: 0)
            with pytest.raises(OwnedByProvider, match=r"Counter"):
                data.create_or_reconfigure_attribute(name, lambda: 0)
            with pytest.raises(OwnedByProvider, match=r"Counter"):
                data.set_static(name, 0)
            assert data.legacy_count == 1

    asyncio.run(scenario())


# --- what a Provider is -----------------------------------------------------------------


def test_a_provider_cannot_declare_provides_itself() -> None:
    with pytest.raises(TypeError, match="Key names its Provider"):

        class _Declares(Provider):  # pyright: ignore[reportUnusedClass]
            provides = (COUNT,)


def test_a_provider_registers_only_keys_it_provides() -> None:
    data = BotData(IGN)
    counter = Counter(data, _Pipe(), None)  # pyright: ignore[reportArgumentType] - never used
    with pytest.raises(ValueError, match=r"Counter.*'double'"):
        counter.register(DOUBLE, lambda: 0)


def test_a_provider_sends_actions_with_no_correlation_id() -> None:
    pipe = _Pipe()
    counter = Counter(BotData(IGN), pipe, None)  # pyright: ignore[reportArgumentType] - never used

    async def _noop() -> None:
        pass

    request = ActionRequest("Counter - fix", _noop, ign=IGN)
    request.correlation_id = "stale"
    counter.send(request)

    assert pipe.sent == [request]
    assert request.correlation_id is None
