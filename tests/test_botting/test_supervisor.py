"""
The Supervisor and Pauses (ADR 0004), driven through real DecisionMakers running
in a real event loop.

Nothing here is faked but the two edges of an Engine: the pipe to Main Process,
which records what is sent instead of sending it, and the telemetry emitter, which
records what is emitted. The Supervisor, the Pauses and the decision loops are the
production ones.

A DecisionMaker is "running" when its loop keeps deciding while the test yields to
the event loop, and "paused" when it does not.
"""

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any

import pytest
from pytest_mock import MockerFixture

from botting.core.action_data import ActionRequest
from botting.core.bot import USER_REQUESTS_PRIORITY, Bot
from botting.core.bot_data import BotData
from botting.core.decision_maker import (
    DecisionLoop,
    DecisionMaker,
    PauseNotDeclared,
    action_name,
)
from botting.core.errors import StartupRefused
from botting.core.supervisor import Supervisor, resolve_pauses
from botting.telemetry_events import (
    DECISION_DISABLED,
    DECISION_ENABLED,
    DECISION_PAUSED,
    DECISION_RESUMED,
)

IGN = "Tester"
HANDLE = 4242


class _Pipe:
    """The Engine's end of the pipe to Main Process: records what is sent."""

    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, obj: object) -> None:
        self.sent.append(obj)


# --- the DecisionMakers -----------------------------------------------------------


class Worker(DecisionMaker):
    """Decides as fast as the event loop lets it, recording each decision."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        self.decisions: list[str | None] = []
        self.starts = 0
        self.stops = 0
        self.state = object()

    def on_start(self) -> None:
        self.starts += 1

    def on_stop(self) -> None:
        self.stops += 1

    async def _decide(self) -> None:
        self.decisions.append(self.correlation_id)
        await asyncio.sleep(0)


class SubWorker(Worker):
    """A Worker subclass: a Pause on `Worker` must leave it running."""


class Idle(DecisionMaker):
    """Never decides twice; only here to hold Pauses from the test."""

    pauses = (Worker, SubWorker, "tests.test_botting.test_supervisor.Absent")

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class OtherIdle(Idle):
    """A second holder."""


class Absent(DecisionMaker):
    """A class the Bots below never run."""

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class Holder(DecisionMaker):
    """Takes one Pause on `Worker`, in its own loop, and holds it until told."""

    pauses = (Worker,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        self.holding = asyncio.Event()
        self.release = asyncio.Event()
        self.took = False

    async def _decide(self) -> None:
        if self.took:
            await asyncio.Event().wait()
        self.took = True
        async with self.pause(Worker, reason="holding"):
            self.holding.set()
            await self.release.wait()


class Boss(DecisionMaker):
    """Pauses the Holder from the test."""

    pauses = (Holder, Worker)

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class Legacy(DecisionMaker):
    """An unported DecisionMaker, driving the shim from the test."""

    async def _decide(self) -> None:
        await asyncio.Event().wait()


class SelfDisabling(Worker):
    """
    Disables itself through the shim on its third decision, as TrialRunner does.
    Throttled like every game DecisionMaker, so the cancellation lands on the
    throttle's sleep.
    """

    _throttle = 0.001

    async def _decide(self) -> None:
        await super()._decide()
        if len(self.decisions) == 3:
            self._disable_decision_makers("SelfDisabling")


class Escalating(Worker):
    """Pauses itself for the user on its third decision, as Escalate does."""

    pauses = ("tests.test_botting.test_supervisor.Escalating",)
    _throttle = 0.001

    async def _decide(self) -> None:
        await super()._decide()
        if len(self.decisions) == 3:
            self.pause_for_user(Escalating, reason="stuck: needs a human")


class Narcissus(Worker):
    """Declares a Pause on its own class."""

    pauses = ("tests.test_botting.test_supervisor.Narcissus",)


class TwoLoops(DecisionMaker):
    """Declares two loops, as SoloRebuff does one per buff."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
        super().__init__(*args, **kwargs)
        self.decisions: dict[str, int] = {"a": 0, "b": 0}

    def loops(self) -> Sequence[DecisionLoop]:
        return [
            DecisionLoop(f"{self} - {name}", lambda name=name: self._one(name))
            for name in self.decisions
        ]

    async def _one(self, name: str) -> None:
        self.decisions[name] += 1
        await asyncio.sleep(0)

    async def _decide(self) -> None:
        raise AssertionError("never called: loops() names the decisions")


class Crashing(DecisionMaker):
    async def _decide(self) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")


# --- harness ----------------------------------------------------------------------


class _Supervised:
    """A running Supervisor and the DecisionMakers it runs, by class."""

    def __init__(
        self, supervisor: Supervisor, pipe: _Pipe, dms: Sequence[DecisionMaker]
    ) -> None:
        self.supervisor = supervisor
        self.pipe = pipe
        self.by_class = {type(dm): dm for dm in dms}

    def __getitem__[T: DecisionMaker](self, cls: type[T]) -> T:
        dm = self.by_class[cls]
        assert isinstance(dm, cls)
        return dm


def _build(*classes: type[DecisionMaker]) -> tuple[list[DecisionMaker], _Pipe]:
    data = BotData(IGN)
    data.set_static("handle", HANDLE)
    pipe = _Pipe()
    dms = [cls({}, data, pipe) for cls in classes]  # pyright: ignore[reportArgumentType] - no Manager: nothing here asks it for a proxy
    return dms, pipe


@contextlib.asynccontextmanager
async def _running(*classes: type[DecisionMaker]) -> AsyncIterator[_Supervised]:
    dms, pipe = _build(*classes)
    supervisor = Supervisor(IGN, dms, resolve_pauses(classes))
    run = asyncio.create_task(supervisor.run())
    await _settle()
    try:
        yield _Supervised(supervisor, pipe, dms)
    finally:
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run


async def _settle(turns: int = 20) -> None:
    """Let every ready task run for a while."""
    for _ in range(turns):
        await asyncio.sleep(0)


async def _is_running(worker: Worker) -> bool:
    before = len(worker.decisions)
    await _settle()
    await asyncio.sleep(0.01)  # a throttled loop sleeps between decisions
    await _settle()
    return len(worker.decisions) > before


async def _eventually(predicate: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Whether `predicate` comes true within `timeout`, yielding all the while."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            return False
        await asyncio.sleep(0.001)
    return True


@pytest.fixture
def emitted(
    mocker: MockerFixture,
) -> list[tuple[str | None, str, Mapping[str, object]]]:
    """Every Telemetry Record the DecisionMakers and the Supervisor emit."""
    records: list[tuple[str | None, str, Mapping[str, object]]] = []

    def record(
        correlation_id: str | None,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        logger_name: str | None = None,
    ) -> None:
        records.append((correlation_id, event_type, dict(payload or {})))

    mocker.patch("botting.core.decision_maker.emit_event", side_effect=record)
    mocker.patch("botting.core.supervisor.emit_event", side_effect=record)
    return records


# --- the Supervisor runs every loop -------------------------------------------------


def test_the_supervisor_runs_every_decision_maker() -> None:
    async def scenario() -> None:
        async with _running(Worker, SubWorker) as bot:
            assert await _is_running(bot[Worker])
            assert await _is_running(bot[SubWorker])
            assert bot[Worker].starts == 1

    asyncio.run(scenario())


def test_a_decision_maker_with_several_loops_runs_them_all_and_pauses_them_together() -> (
    None
):
    async def scenario() -> None:
        async with _running(TwoLoops, Idle) as bot:
            loops = bot[TwoLoops]
            await _settle()
            assert loops.decisions["a"] > 0
            assert loops.decisions["b"] > 0

            # Idle declares no Pause on TwoLoops; the Supervisor holds the Pause.
            pause = bot.supervisor.pause_for_user(reason="test")
            await _settle()
            counts = dict(loops.decisions)
            await _settle()
            assert loops.decisions == counts

            for held in pause:
                bot.supervisor.release(held)
            await _settle()
            assert loops.decisions["a"] > counts["a"]
            assert loops.decisions["b"] > counts["b"]

    asyncio.run(scenario())


def test_a_loop_that_raises_still_ends_the_bot() -> None:
    async def scenario() -> None:
        dms, _ = _build(Crashing, Worker)
        supervisor = Supervisor(IGN, dms, resolve_pauses([Crashing, Worker]))
        with pytest.raises(ExceptionGroup) as raised:
            await asyncio.wait_for(supervisor.run(), timeout=5)
        assert raised.group_contains(RuntimeError, match="boom")

    asyncio.run(scenario())


def test_on_stop_runs_once_the_loops_stop_by_any_route() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            worker = bot[Worker]
            async with bot[Idle].pause(Worker, reason="test"):
                await _settle()
                assert worker.stops == 1
            await _settle()
            assert worker.stops == 1
            assert worker.starts == 2
        # The Bot ending stops the loops too.
        assert worker.stops == 2

    asyncio.run(scenario())


# --- Pauses stack, and are scoped ---------------------------------------------------


def test_two_holders_pause_x_and_x_stays_paused_until_both_release() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle, OtherIdle) as bot:
            worker = bot[Worker]
            first = bot[Idle].pause(Worker, reason="first")
            second = bot[OtherIdle].pause(Worker, reason="second")

            await first.__aenter__()
            await second.__aenter__()
            assert not await _is_running(worker)

            await first.__aexit__(None, None, None)
            assert not await _is_running(worker)

            await second.__aexit__(None, None, None)
            assert await _is_running(worker)

    asyncio.run(scenario())


def test_a_holder_whose_block_raises_releases_its_pause() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            paused: list[bool] = []

            async def fail_half_way() -> None:
                async with bot[Idle].pause(Worker, reason="test"):
                    paused.append(not await _is_running(bot[Worker]))
                    raise RuntimeError("half-way")

            with pytest.raises(RuntimeError, match="half-way"):
                await fail_half_way()
            assert paused == [True]
            assert await _is_running(bot[Worker])

    asyncio.run(scenario())


def test_a_holder_whose_block_is_cancelled_releases_its_pause() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            holding = asyncio.Event()

            async def hold() -> None:
                async with bot[Idle].pause(Worker, reason="test"):
                    holding.set()
                    await asyncio.Event().wait()

            task = asyncio.create_task(hold())
            await holding.wait()
            assert not await _is_running(bot[Worker])

            task.cancel()
            assert await _is_running(bot[Worker])

    asyncio.run(scenario())


def test_a_holder_that_is_itself_paused_releases_the_pauses_it_holds() -> None:
    async def scenario() -> None:
        async with _running(Worker, Holder, Boss) as bot:
            holder = bot[Holder]
            await holder.holding.wait()
            assert not await _is_running(bot[Worker])

            async with bot[Boss].pause(Holder, reason="takeover"):
                # The Holder's decision is cancelled, so its block exits and the
                # Worker is free; the Holder itself stays paused.
                assert await _is_running(bot[Worker])
                assert bot.supervisor.held(Holder)
                assert not bot.supervisor.held(Worker)

    asyncio.run(scenario())


def test_a_paused_decision_maker_keeps_its_state_and_restarts_fresh() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            worker = bot[Worker]
            state = worker.state
            async with bot[Idle].pause(Worker, reason="test"):
                await _settle()
                before = list(worker.decisions)
                assert worker.starts == 1

            await _settle()
            assert bot[Worker] is worker
            assert worker.state is state
            assert worker.starts == 2, "on_start runs again before the restart"
            resumed = worker.decisions[len(before)]
            assert resumed is not None
            assert resumed not in before, "the restarted loop mints a fresh id"

    asyncio.run(scenario())


# --- what a Pause may name ----------------------------------------------------------


def test_pausing_an_undeclared_class_raises() -> None:
    async def scenario() -> None:
        async with _running(Worker, Holder, Idle) as bot:
            with pytest.raises(PauseNotDeclared, match="Idle"):
                async with bot[Holder].pause(Idle, reason="test"):
                    pass
            with pytest.raises(PauseNotDeclared, match="Idle"):
                bot[Holder].pause_for_user(Idle, reason="test")
            assert not bot.supervisor.held(Idle)

    asyncio.run(scenario())


def test_pausing_a_class_the_bot_does_not_run_does_nothing(
    emitted: list[tuple[str | None, str, Mapping[str, object]]],
) -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            async with bot[Idle].pause(Absent, reason="test"):
                assert await _is_running(bot[Worker])
            assert emitted == []

    asyncio.run(scenario())


def test_a_pause_on_a_class_does_not_pause_its_subclass() -> None:
    async def scenario() -> None:
        async with (
            _running(Worker, SubWorker, Idle) as bot,
            bot[Idle].pause(Worker, reason="test"),
        ):
            assert not await _is_running(bot[Worker])
            assert await _is_running(bot[SubWorker])

    asyncio.run(scenario())


def test_a_decision_maker_cannot_hold_a_scoped_pause_on_itself() -> None:
    async def scenario() -> None:
        async with _running(Narcissus) as bot:
            with pytest.raises(ValueError, match="its own class"):
                async with bot[Narcissus].pause(Narcissus, reason="test"):
                    pass
            assert await _is_running(bot[Narcissus])

    asyncio.run(scenario())


def test_a_dotted_path_entry_resolves_to_its_class() -> None:
    assert resolve_pauses([Idle])[Idle] == frozenset({Worker, SubWorker, Absent})


@pytest.mark.parametrize(
    "entry",
    [
        "tests.test_botting.test_supervisor.Nowhere",
        "tests.test_botting.no_such_module.Worker",
        "Worker",
        "tests.test_botting.test_supervisor.IGN",
    ],
)
def test_a_pauses_entry_that_resolves_to_nothing_refuses_the_start(entry: str) -> None:
    class Miswired(Idle):
        pauses = (entry,)

    with pytest.raises(StartupRefused, match=entry.replace(".", r"\.")):
        resolve_pauses([Worker, Miswired])


# --- cancel_actions -----------------------------------------------------------------


def test_cancel_actions_sends_one_request_cancelling_the_targets_actions() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            async with bot[Idle].pause(Worker, reason="test", cancel_actions=True):
                pass
            [request] = bot.pipe.sent
            assert isinstance(request, ActionRequest)
            assert request.cancel_tasks == [action_name(Worker, IGN)]
            assert request.cancel_tasks == [repr(bot[Worker])]

    asyncio.run(scenario())


def test_a_pause_sends_nothing_to_main_process_by_default() -> None:
    async def scenario() -> None:
        async with _running(Worker, Idle) as bot:
            async with bot[Idle].pause(Worker, reason="test"):
                await _settle()
            bot[Idle].pause_for_user(Worker, reason="test")
            await _settle()
            assert bot.pipe.sent == []

    asyncio.run(scenario())


def test_action_name_is_what_a_decision_maker_names_its_own_requests() -> None:
    [worker], _ = _build(Worker)
    assert action_name(Worker, IGN) == "Worker(Tester)" == repr(worker)


# --- telemetry ----------------------------------------------------------------------


def test_a_pause_is_recorded_when_taken_and_when_released(
    emitted: list[tuple[str | None, str, Mapping[str, object]]],
) -> None:
    async def scenario() -> None:
        async with (
            _running(Worker, Idle) as bot,
            bot[Idle].pause(Worker, reason="no mobs"),
        ):
            pass

    asyncio.run(scenario())
    expected = {"target": "Worker", "holder": "Idle(Tester)", "reason": "no mobs"}
    assert [(event, payload) for _, event, payload in emitted] == [
        (DECISION_PAUSED, expected),
        (DECISION_RESUMED, expected),
    ]


# --- the user -----------------------------------------------------------------------


class _TestBot(Bot):
    def __init__(self, *classes: type[DecisionMaker]) -> None:
        super().__init__(IGN, {})  # pyright: ignore[reportArgumentType] - no Manager needed
        self.classes = list(classes)

    def find_handle(self) -> int:
        return HANDLE

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return self.classes


@contextlib.asynccontextmanager
async def _bot(*classes: type[DecisionMaker]) -> AsyncIterator[tuple[_TestBot, _Pipe]]:
    """A Bot started as an Engine starts it, minus the process around it."""
    bot = _TestBot(*classes)
    pipe = _Pipe()
    bot.data = BotData(IGN)
    bot.data.set_static("handle", HANDLE)
    bot.pipe = pipe  # pyright: ignore[reportAttributeAccessIssue] - records instead of sending
    bot.barrier = threading.Barrier(1)
    run = asyncio.create_task(bot.start())
    await _settle()
    try:
        yield bot, pipe
    finally:
        run.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await run


def _dm[T: DecisionMaker](bot: Bot, cls: type[T]) -> T:
    [dm] = [dm for dm in bot.decision_makers if type(dm) is cls]
    assert isinstance(dm, cls)
    return dm


async def _wait_running(worker: Worker) -> bool:
    """Whether `worker` starts deciding, allowing for the start barrier's thread hop."""
    return await _eventually(lambda: len(worker.decisions) > 0)


def test_discord_pause_pauses_every_decision_maker_until_resume() -> None:
    async def scenario() -> None:
        async with _bot(Worker, SubWorker) as (bot, _):
            worker, sub = _dm(bot, Worker), _dm(bot, SubWorker)
            assert await _wait_running(worker)

            bot.pause()
            assert not await _is_running(worker)
            assert not await _is_running(sub)

            bot.resume()
            assert await _is_running(worker)
            assert await _is_running(sub)

    asyncio.run(scenario())


def test_discord_pause_sends_the_movement_key_release_it_always_has() -> None:
    async def scenario() -> None:
        async with _bot(Worker) as (bot, pipe):
            assert await _wait_running(_dm(bot, Worker))
            bot.pause()
            [request] = pipe.sent
            assert isinstance(request, ActionRequest)
            assert request.identifier == f"Releasing movement keys - {IGN}"
            assert request.procedure == Bot._release_movement_keys  # pyright: ignore[reportPrivateUsage]
            assert request.ign == IGN
            assert request.priority == USER_REQUESTS_PRIORITY == 98
            assert request.requeue_if_not_scheduled is False
            assert request.cancels_itself is True
            assert request.cancel_tasks == []
            assert request.args == (HANDLE,)

    asyncio.run(scenario())


def test_discord_pause_and_resume_are_recorded_as_user_held_pauses(
    emitted: list[tuple[str | None, str, Mapping[str, object]]],
) -> None:
    async def scenario() -> None:
        async with _bot(Worker) as (bot, _):
            assert await _wait_running(_dm(bot, Worker))
            bot.pause()
            bot.resume()

    asyncio.run(scenario())
    expected = {"target": "Worker", "holder": "user", "reason": "Discord PAUSE"}
    assert emitted == [
        (None, DECISION_PAUSED, expected),
        (None, DECISION_RESUMED, expected),
    ]


def test_resume_releases_user_held_pauses_but_not_scoped_ones() -> None:
    async def scenario() -> None:
        async with _bot(Worker, Idle) as (bot, _):
            worker = _dm(bot, Worker)
            assert await _wait_running(worker)
            async with _dm(bot, Idle).pause(Worker, reason="test"):
                bot.pause()
                bot.resume()
                assert not await _is_running(worker)
            assert await _is_running(worker)

    asyncio.run(scenario())


def test_pause_for_user_holds_until_resume_and_nothing_else() -> None:
    async def scenario() -> None:
        async with _bot(Worker, Holder) as (bot, _):
            worker = _dm(bot, Worker)
            holder = _dm(bot, Holder)
            await holder.holding.wait()
            holder.pause_for_user(Worker, reason="stuck: needs a human")

            # The Holder's own scoped Pause ends; the user-held one does not.
            holder.release.set()
            assert not await _is_running(worker)
            # Nor does the shim's enable, nor the holder being paused.
            holder._enable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            assert not await _is_running(worker)

            bot.resume()
            assert await _is_running(worker)

    asyncio.run(scenario())


def test_a_decision_maker_may_pause_itself_for_the_user() -> None:
    async def scenario() -> None:
        async with _bot(Escalating) as (bot, _):
            dm = _dm(bot, Escalating)
            assert await _eventually(lambda: len(dm.decisions) >= 3)
            assert not await _is_running(dm)
            assert len(dm.decisions) == 3

            bot.resume()
            assert await _eventually(lambda: len(dm.decisions) > 3)

    asyncio.run(scenario())


# --- the legacy shim ----------------------------------------------------------------


def test_the_shim_disables_until_the_matching_enable(
    emitted: list[tuple[str | None, str, Mapping[str, object]]],
) -> None:
    async def scenario() -> None:
        async with _running(Worker, Legacy) as bot:
            legacy = bot[Legacy]
            legacy._disable_decision_makers("Worker", "Absent")  # pyright: ignore[reportPrivateUsage]
            assert not await _is_running(bot[Worker])
            legacy._enable_decision_makers("Worker", "Absent")  # pyright: ignore[reportPrivateUsage]
            assert await _is_running(bot[Worker])

    asyncio.run(scenario())
    # Today's records, for the classes this Bot runs only, and no Pause records.
    assert [(event, payload) for _, event, payload in emitted] == [
        (DECISION_DISABLED, {"target": "Worker"}),
        (DECISION_ENABLED, {"target": "Worker"}),
    ]


def test_one_shim_enable_undoes_any_number_of_disables_whoever_took_them() -> None:
    class OtherLegacy(Legacy):
        pass

    async def scenario() -> None:
        async with _running(Worker, Legacy, OtherLegacy) as bot:
            bot[Legacy]._disable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            bot[OtherLegacy]._disable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            bot[Legacy]._disable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            assert not await _is_running(bot[Worker])
            bot[OtherLegacy]._enable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            assert await _is_running(bot[Worker])

    asyncio.run(scenario())


def test_a_shim_pause_survives_its_holder_being_paused() -> None:
    async def scenario() -> None:
        async with _running(Worker, Legacy, Idle) as bot:
            bot[Legacy]._disable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            pause = bot.supervisor.pause_for_user(reason="test")
            for held in pause:
                bot.supervisor.release(held)
            assert not await _is_running(bot[Worker])

    asyncio.run(scenario())


def test_a_decision_maker_may_disable_itself_through_the_shim() -> None:
    async def scenario() -> None:
        async with _running(SelfDisabling) as bot:
            dm = bot[SelfDisabling]
            assert await _eventually(lambda: len(dm.decisions) >= 3)
            assert not await _is_running(dm)
            assert len(dm.decisions) == 3
            assert dm.starts == 1

            dm._enable_decision_makers("SelfDisabling")  # pyright: ignore[reportPrivateUsage]
            assert await _eventually(lambda: len(dm.decisions) > 3)
            assert dm.starts == 2

    asyncio.run(scenario())


def test_resume_ends_shim_pauses() -> None:
    async def scenario() -> None:
        async with _bot(Worker, Legacy) as (bot, _):
            worker = _dm(bot, Worker)
            assert await _wait_running(worker)
            _dm(bot, Legacy)._disable_decision_makers("Worker")  # pyright: ignore[reportPrivateUsage]
            assert not await _is_running(worker)
            bot.resume()
            assert await _is_running(worker)

    asyncio.run(scenario())


# --- assembly -----------------------------------------------------------------------


def test_a_miswired_pauses_entry_refuses_the_start_before_any_decision_maker_is_built() -> (
    None
):
    class Unbuildable(Idle):
        pauses = ("tests.test_botting.test_supervisor.Nowhere",)

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401 - DecisionMaker's own
            raise AssertionError("built before the declarations were checked")

    async def scenario() -> None:
        bot = _TestBot(Worker, Unbuildable)
        bot.data = BotData(IGN)
        bot.pipe = _Pipe()  # pyright: ignore[reportAttributeAccessIssue] - never sent to
        bot.barrier = threading.Barrier(1)
        with pytest.raises(StartupRefused, match="Unbuildable.*Nowhere"):
            await bot.start()

    asyncio.run(scenario())
