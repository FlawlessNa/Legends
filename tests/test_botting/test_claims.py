"""
Claims (ADR 0004), driven through a real Bot's `start`.

Nothing here is faked but the edges of an Engine: the pipe to Main Process, the
clock, which the test advances, and the telemetry emitter, which records. The
Bot, assembly, the Supervisor, `BotData` and the Claims are the production ones;
the Provider and the DecisionMakers are defined here.

`Counter` serves its own value, which goes up by one at every refresh; a Claim
serves its source's, which the tests tell apart from the Provider's.
"""

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

import pytest
from pytest_mock import MockerFixture

from botting.core.bot import Bot
from botting.core.bot_data import BotData
from botting.core.claims import ClaimHeld, ClaimNotDeclared, fixed, following
from botting.core.data_keys import Key, Provider
from botting.core.decision_maker import DecisionMaker
from botting.core.errors import DecisionMakerCrashed, StartupRefused
from botting.core.supervisor import USER, Pause, PauseKind
from botting.telemetry_events import DATA_CLAIMED, DATA_RELEASED

IGN = "Tester"
HANDLE = 4242


class _Pipe:
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


# --- the Provider -----------------------------------------------------------------


class Counter(Provider):
    """Serves COUNT, its own refresh count, refreshed every second, and FIXED."""

    def __init__(self, *args: Any, **settings: object) -> None:  # noqa: ANN401 - Provider's own
        super().__init__(*args, **settings)
        self.updates = 0

    def setup(self) -> None:
        self.register(COUNT, self._next, threshold=1.0)
        self.register(FIXED, lambda: 0)

    def _next(self) -> int:
        self.updates += 1
        return self.updates


COUNT: Key[int] = Key("count", provider=Counter, steerable=True)
#: Not steerable: nothing may claim it.
FIXED: Key[int] = Key("fixed", provider=Counter)


# --- the DecisionMakers -------------------------------------------------------------


class Idle(DecisionMaker):
    """Never decides twice; its Claims are taken from the test."""

    steers = (COUNT,)

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class OtherIdle(Idle):
    """A second holder."""


class Reader(DecisionMaker):
    """Reads COUNT and nothing else; declares no `steers`."""

    reads = (COUNT,)

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class Raiser(DecisionMaker):
    """Claims COUNT in its first decision, then raises."""

    steers = (COUNT,)

    async def _decide(self) -> None:
        async with self.claim(COUNT, fixed(-1), reason="about to crash"):
            await asyncio.sleep(0)
            raise RuntimeError("boom")


class RunHolder(DecisionMaker):
    """Holds a Claim on COUNT for as long as its loop runs (`holds_for_run`)."""

    steers = (COUNT,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        self.raise_next = False

    def holds_for_run(self) -> AbstractAsyncContextManager[object]:
        return self.claim(COUNT, fixed(-7), reason="for the run")

    async def _decide(self) -> None:
        await asyncio.sleep(0)
        if self.raise_next:
            raise RuntimeError("boom")


class Unsteerable(DecisionMaker):
    steers = (FIXED,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        raise AssertionError("never built")

    async def _decide(self) -> None:
        raise AssertionError("never runs")


# --- the Bot ------------------------------------------------------------------------


class _TestBot(Bot):
    def __init__(self, *classes: type[DecisionMaker]) -> None:
        super().__init__(IGN, {})  # pyright: ignore[reportArgumentType] - no Manager needed
        self.classes = list(classes)

    def find_handle(self) -> int:
        return HANDLE

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return self.classes


def _prepared(bot: _TestBot, clock: FakeClock) -> None:
    bot.data = BotData(IGN, clock=clock)
    bot.data.set_static("handle", HANDLE)
    bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue] - records instead of sending
    bot.barrier = threading.Barrier(1)


@contextlib.asynccontextmanager
async def _started(
    *classes: type[DecisionMaker], clock: FakeClock | None = None
) -> AsyncIterator[_TestBot]:
    """A Bot started as an Engine starts it, minus the process around it."""
    bot = _TestBot(*classes)
    _prepared(bot, clock or FakeClock())
    run = asyncio.create_task(bot.start())
    while bot.supervisor is None and not run.done():
        await asyncio.sleep(0)
    if run.done():
        run.result()
    await _settle()
    try:
        yield bot
    finally:
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run


async def _settle(turns: int = 20) -> None:
    for _ in range(turns):
        await asyncio.sleep(0)


def _dm[T: DecisionMaker](bot: Bot, cls: type[T]) -> T:
    [dm] = [dm for dm in bot.decision_makers if type(dm) is cls]
    assert isinstance(dm, cls)
    return dm


def _data(bot: Bot) -> BotData:
    assert bot.data is not None
    return bot.data


@pytest.fixture
def emitted(
    mocker: MockerFixture,
) -> list[tuple[str, Mapping[str, object]]]:
    """Every Telemetry Record the DecisionMakers emit."""
    records: list[tuple[str, Mapping[str, object]]] = []

    def record(
        correlation_id: str | None,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        logger_name: str | None = None,
    ) -> None:
        records.append((event_type, dict(payload or {})))

    mocker.patch("botting.core.decision_maker.emit_event", side_effect=record)
    return records


# --- what a Claim serves --------------------------------------------------------------


def test_a_claimed_key_serves_its_source_and_its_providers_own_value_after() -> None:
    async def scenario() -> None:
        async with _started(Idle, Reader) as bot:
            idle, reader = _dm(bot, Idle), _dm(bot, Reader)
            assert reader.read(COUNT) == 1

            async with idle.claim(COUNT, fixed(-1), reason="test"):
                assert reader.read(COUNT) == -1
                assert reader.refresh(COUNT) == -1

            assert reader.read(COUNT) == 1
            assert reader.refresh(COUNT) == 2

    asyncio.run(scenario())


def test_while_claimed_the_key_refreshes_on_its_own_threshold_from_the_source() -> None:
    clock = FakeClock()
    calls: list[int] = []

    def source() -> int:
        calls.append(len(calls))
        return 100 + len(calls)

    async def scenario() -> None:
        async with _started(Idle, Reader, clock=clock) as bot:
            idle, reader = _dm(bot, Idle), _dm(bot, Reader)
            async with idle.claim(COUNT, following(source), reason="test"):
                assert reader.read(COUNT) == 101, "refreshed when taken"
                clock.advance(0.5)
                assert reader.read(COUNT) == 101, "within its threshold"
                clock.advance(0.6)
                assert reader.read(COUNT) == 102, "past its 1 s threshold"
            assert len(calls) == 2
            counter = next(p for p in bot.providers if isinstance(p, Counter))
            assert counter.updates == 1, "the Provider's own update never ran"

    asyncio.run(scenario())


def test_a_second_claim_on_a_held_key_raises_claim_held_naming_the_holder() -> None:
    async def scenario() -> None:
        async with _started(Idle, OtherIdle, Reader) as bot:
            idle, other = _dm(bot, Idle), _dm(bot, OtherIdle)
            async with idle.claim(COUNT, fixed(-1), reason="first"):
                with pytest.raises(ClaimHeld) as held:
                    async with other.claim(COUNT, fixed(-2), reason="second"):
                        pytest.fail("a second holder entered the block")
                assert f"Idle({IGN})" in str(held.value)
                assert "first" in str(held.value)
                assert _dm(bot, Reader).read(COUNT) == -1, "the first still holds"

    asyncio.run(scenario())


def test_a_claimed_key_cannot_be_written_around_its_claim() -> None:
    """Neither a Provider's `store` nor a write by the key's name undoes a Claim."""

    async def scenario() -> None:
        async with _started(Idle, Reader) as bot:
            data = _data(bot)
            async with _dm(bot, Idle).claim(COUNT, fixed(-1), reason="held"):
                with pytest.raises(ClaimHeld, match="held"):
                    data.store(COUNT, 5)
                with pytest.raises(ClaimHeld, match="held"):
                    data.count = 5
                assert _dm(bot, Reader).read(COUNT) == -1
            data.count = 5
            assert _dm(bot, Reader).read(COUNT) == 5

    asyncio.run(scenario())


def test_a_claim_whose_block_raises_is_released() -> None:
    async def scenario() -> None:
        async with _started(Idle, OtherIdle, Reader) as bot:
            idle, reader = _dm(bot, Idle), _dm(bot, Reader)
            with pytest.raises(RuntimeError):
                async with idle.claim(COUNT, fixed(-1), reason="test"):
                    raise RuntimeError("boom")

            assert _data(bot).claim_on(COUNT) is None
            assert reader.read(COUNT) == 1
            async with _dm(bot, OtherIdle).claim(COUNT, fixed(-2), reason="next"):
                assert reader.read(COUNT) == -2

    asyncio.run(scenario())


def test_a_claim_whose_block_is_cancelled_is_released() -> None:
    async def scenario() -> None:
        async with _started(Idle, Reader) as bot:
            idle, reader = _dm(bot, Idle), _dm(bot, Reader)
            holding = asyncio.Event()

            async def hold() -> None:
                async with idle.claim(COUNT, fixed(-1), reason="test"):
                    holding.set()
                    await asyncio.Event().wait()

            task = asyncio.create_task(hold())
            await holding.wait()
            assert reader.read(COUNT) == -1
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            assert _data(bot).claim_on(COUNT) is None
            assert reader.read(COUNT) == 1

    asyncio.run(scenario())


def test_claim_and_release_are_recorded(
    emitted: list[tuple[str, Mapping[str, object]]],
) -> None:
    async def scenario() -> None:
        async with (
            _started(Idle) as bot,
            _dm(bot, Idle).claim(COUNT, fixed(-1), reason="test"),
        ):
            pass

    asyncio.run(scenario())

    payload = {"key": "count", "holder": f"Idle({IGN})", "reason": "test"}
    assert [e for e in emitted if e[0] in (DATA_CLAIMED, DATA_RELEASED)] == [
        (DATA_CLAIMED, payload),
        (DATA_RELEASED, payload),
    ]


# --- what is refused ------------------------------------------------------------------


def test_claiming_a_key_steers_does_not_declare_raises() -> None:
    async def scenario() -> None:
        async with _started(Idle, Reader) as bot:
            with pytest.raises(ClaimNotDeclared, match="'count'"):
                async with _dm(bot, Reader).claim(COUNT, fixed(-1), reason="test"):
                    pytest.fail("an undeclared Claim entered the block")
            assert _data(bot).claim_on(COUNT) is None

    asyncio.run(scenario())


def test_steering_a_key_that_is_not_steerable_is_refused_at_assembly() -> None:
    bot = _TestBot(Idle, Unsteerable)
    _prepared(bot, FakeClock())

    with pytest.raises(StartupRefused) as refused:
        asyncio.run(asyncio.wait_for(bot.start(), timeout=5))

    assert "Unsteerable" in str(refused.value)
    assert "'fixed'" in str(refused.value)
    assert bot.providers == [], "refused before any Provider is built"


def test_a_steered_key_has_its_provider_built() -> None:
    async def scenario() -> None:
        async with _started(Idle) as bot:
            assert [type(p) for p in bot.providers if isinstance(p, Counter)] == [
                Counter
            ]
            assert _dm(bot, Idle).read(COUNT) == 1, "a steered key may be read"

    asyncio.run(scenario())


# --- a Claim held for a run -------------------------------------------------------------


def test_a_claim_held_for_the_run_is_released_by_a_pause_and_taken_on_resume() -> None:
    async def scenario() -> None:
        async with _started(RunHolder, Reader) as bot:
            reader, supervisor = _dm(bot, Reader), bot.supervisor
            assert supervisor is not None
            assert reader.read(COUNT) == -7

            pause = Pause(supervisor.target(RunHolder), USER, "test", PauseKind.SCOPED)
            supervisor.hold(pause)
            await _settle()
            assert _data(bot).claim_on(COUNT) is None
            assert reader.read(COUNT) == 1

            supervisor.release(pause)
            await _settle()
            assert reader.read(COUNT) == -7

    asyncio.run(scenario())


# --- crashes ----------------------------------------------------------------------------


async def _crash_of(*classes: type[DecisionMaker]) -> _TestBot:
    bot = _TestBot(*classes)
    _prepared(bot, FakeClock())
    with pytest.raises(ExceptionGroup) as raised:
        await asyncio.wait_for(bot.start(), timeout=5)
    [crash] = raised.value.exceptions
    assert isinstance(crash, DecisionMakerCrashed)
    return bot


def test_a_crashing_decision_makers_claims_are_released_before_the_bot_ends() -> None:
    async def scenario() -> None:
        bot = await _crash_of(Raiser, Reader)
        assert _data(bot).claim_on(COUNT) is None
        assert _data(bot).read(COUNT) == 1

    asyncio.run(scenario())


def test_a_claim_held_for_the_run_is_released_when_the_loop_crashes() -> None:
    async def scenario() -> None:
        bot = _TestBot(RunHolder, Reader)
        _prepared(bot, FakeClock())
        run = asyncio.create_task(bot.start())
        while bot.supervisor is None:
            await asyncio.sleep(0)
        await _settle()
        assert _data(bot).claim_on(COUNT) is not None
        _dm(bot, RunHolder).raise_next = True
        with pytest.raises(ExceptionGroup):
            await asyncio.wait_for(run, timeout=5)
        assert _data(bot).claim_on(COUNT) is None

    asyncio.run(scenario())
