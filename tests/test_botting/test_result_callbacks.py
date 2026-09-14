"""
`ActionRequest.result_callbacks`: a completed procedure's return value handed back
to the DecisionMaker that asked for it.

This is the narrow slice of `_cleanup_handler`'s long-standing "handling of future
result back to the DecisionMaker" TODO that movement recovery's **Delivery Gate**
needs. A DecisionMaker decides in an Engine; the Input Sequence is compiled and sent
in Main Process (ADR 0002), so the number of Steps that actually reached the client
is knowable only here.

What it must *not* do is report a cancelled Action. Preemption stops the Stuck
clocks by construction, and a preempted send loop has no return value describing its
Delivered Prefix anyway - so silence is the honest reading, not a gap to paper over.
"""

import asyncio
from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from botting.core.action_data import ActionRequest
from botting.core.async_task_manager import AsyncTaskManager


@pytest.fixture
def manager(mocker: MockerFixture) -> AsyncTaskManager:
    """An AsyncTaskManager with telemetry silenced - `action.*` is not this file's."""
    mocker.patch("botting.core.async_task_manager.emit_event")
    return AsyncTaskManager(mocker.Mock())


def _request(
    procedure: Callable[..., object],
    *,
    result_callbacks: list[Callable[[object], object]] | None = None,
    callbacks: list[Callable[[], object]] | None = None,
) -> ActionRequest:
    return ActionRequest(
        "Rotation(Tester)",
        procedure,
        "Tester",
        result_callbacks=result_callbacks or [],
        callbacks=callbacks or [],
    )


async def _delivers(count: int = 7) -> int:
    """Stands in for `controller.compile_and_send`, which returns a Step count."""
    return count


async def _never_returns() -> int:
    await asyncio.sleep(60)
    return 99


async def _raises() -> int:
    raise RuntimeError("the client went away")


def _run(
    manager: AsyncTaskManager,
    request: ActionRequest,
    then: Callable[[ActionRequest], None] | None = None,
) -> None:
    async def _main() -> None:
        await manager._schedule_task(request)
        assert request.task is not None
        if then is not None:
            then(request)
        try:
            await request.task
        except asyncio.CancelledError, RuntimeError:
            pass
        # Done-callbacks are scheduled on the loop, not run inline.
        await asyncio.sleep(0)

    asyncio.run(_main())


def test_a_completed_procedures_return_value_reaches_the_callback(
    manager: AsyncTaskManager,
) -> None:
    reported: list[object] = []

    _run(manager, _request(_delivers, result_callbacks=[reported.append]))

    assert reported == [7]


def test_a_cancelled_task_reports_nothing(manager: AsyncTaskManager) -> None:
    """
    The reading the Delivery Gate wants. A preempted movement Action delivered
    some prefix of its Input Sequence, but counting it would charge the rotation
    for time another DecisionMaker took away from it.
    """
    reported: list[object] = []

    def _preempt(request: ActionRequest) -> None:
        assert request.task is not None
        request.task.cancel()

    _run(
        manager,
        _request(_never_returns, result_callbacks=[reported.append]),
        then=_preempt,
    )

    assert reported == []


def test_a_raising_task_reports_nothing(manager: AsyncTaskManager) -> None:
    reported: list[object] = []

    _run(manager, _request(_raises, result_callbacks=[reported.append]))

    assert reported == []


def test_a_raising_task_still_signals_the_session(manager: AsyncTaskManager) -> None:
    """
    `_cleanup_handler`'s existing contract, and the one this change could most
    easily have broken: a task that raised puts None on the queue, which is how
    the Task Manager - and with it the Session - is brought down rather than
    limping on. Reading the result before checking for an exception would raise
    on the way there and skip the signal entirely.
    """
    _run(manager, _request(_raises, result_callbacks=[lambda _result: None]))

    assert manager.queue.get_nowait() is None


def test_a_callback_that_raises_does_not_take_the_session_with_it(
    manager: AsyncTaskManager,
) -> None:
    """
    This runs in a done-callback, where a raise has no caller to catch it and is
    swallowed by the event loop's exception handler - so the failure would be
    invisible *and* would skip every callback after it.
    """
    reported: list[object] = []

    def _explode(_result: object) -> None:
        raise ValueError("bad proxy")

    _run(
        manager,
        _request(_delivers, result_callbacks=[_explode, reported.append]),
    )

    assert reported == [7]


def test_ordinary_callbacks_still_fire_and_take_no_argument(
    manager: AsyncTaskManager,
) -> None:
    """
    `callbacks` is the pre-existing list - `Rotation` releases its lock through
    it - and it fires on the blocked path too. The two lists are separate for
    that reason, and this is what breaks if they are ever merged.
    """
    released: list[str] = []

    _run(
        manager,
        _request(_delivers, callbacks=[lambda: released.append("released")]),
    )

    assert released == ["released"]


def test_a_request_with_no_result_callbacks_is_untouched(
    manager: AsyncTaskManager,
) -> None:
    _run(manager, _request(_delivers))

    assert manager.running_tasks == {}
