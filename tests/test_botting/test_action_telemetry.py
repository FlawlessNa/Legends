"""
Tests for the `action.*` Telemetry Records Main Process emits as it disposes of
an ActionRequest.

These are the records that close the Correlation ID chain: a DecisionMaker's own
records say what it decided, and these say what became of it. That is the whole
reason `ActionRequest` carries a Correlation ID, so the propagation is pinned
here rather than left to the call sites.

The records replaced four text logs gated on a per-request `log` flag - severity
and visibility conflated at the call site, which ADR-0001 undoes. Emission is
therefore unconditional, and the flag is gone; the tests below are what fails if
either comes back.
"""

import asyncio
import dataclasses
from typing import Any

import pytest
from pytest_mock import MockerFixture, MockType

from botting.core.action_data import ActionRequest
from botting.core.async_task_manager import AsyncTaskManager
from botting.telemetry_events import (
    ACTION_BLOCKED,
    ACTION_CANCELS_OTHER,
    ACTION_FINISHED,
    ACTION_REQUEUED,
    ACTION_SCHEDULED,
    ACTION_SELF_CANCELLED,
)


async def _noop() -> None:
    """The procedure a scheduled request runs. Nothing here touches a client."""


def _request(identifier: str = "Rotation(Tester)", **fields: object) -> ActionRequest:
    """A request running `_noop`, with any of its fields overridden."""
    return dataclasses.replace(ActionRequest(identifier, _noop, "Tester"), **fields)


class _SpiedManager(AsyncTaskManager):
    """An AsyncTaskManager carrying the spy on its `emit_event`."""

    emitted: MockType


@pytest.fixture
def manager(mocker: MockerFixture) -> _SpiedManager:
    """
    :return: An AsyncTaskManager whose `emit_event` is a spy, exposed as
        `manager.emitted`.
    """
    manager = _SpiedManager(mocker.Mock())
    manager.emitted = mocker.patch("botting.core.async_task_manager.emit_event")
    return manager


def _only_call(manager: _SpiedManager) -> tuple[Any, Any, Any]:
    args, _ = manager.emitted.call_args
    correlation_id, event_type, payload = args[:3]
    return correlation_id, event_type, payload


# --- the envelope a dispatch record carries -------------------------------


def test_the_record_carries_the_requests_correlation_id(manager: _SpiedManager) -> None:
    request = _request(correlation_id="decision-1", priority=7)

    manager._emit(ACTION_SCHEDULED, request)

    correlation_id, event_type, payload = _only_call(manager)
    assert correlation_id == "decision-1"
    assert event_type == ACTION_SCHEDULED
    assert payload == {"identifier": "Rotation(Tester)", "priority": 7}


def test_a_request_no_decision_caused_correlates_nothing(
    manager: _SpiedManager,
) -> None:
    """
    Null rather than a synthesised id: a record that ties to no decision says so.
    """
    manager._emit(ACTION_SCHEDULED, _request())

    correlation_id, _, _ = _only_call(manager)
    assert correlation_id is None


def test_the_priority_is_a_builtin_int(manager: _SpiedManager) -> None:
    """Payloads carry JSON primitives, converted at the call site."""
    manager._emit(ACTION_SCHEDULED, _request(priority=3))

    _, _, payload = _only_call(manager)
    assert type(payload["priority"]) is int


# --- one record per disposal ----------------------------------------------


def test_a_scheduled_request_is_recorded(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    mocker.patch.object(manager, "_schedule_task", mocker.AsyncMock())

    asyncio.run(manager._handle_priority(_request(priority=5)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_SCHEDULED


def test_a_requeued_request_is_recorded(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    mocker.patch.object(manager, "_get_priority_blocking", return_value=99)

    asyncio.run(manager._handle_priority(_request(requeue_if_not_scheduled=True)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_REQUEUED


def test_a_blocked_request_is_recorded(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    """
    The branch a lower-priority request dies in. It is the most analytically
    interesting of the four and the one whose text log was never gated, so it
    would be the easiest to leave behind.
    """
    mocker.patch.object(manager, "_get_priority_blocking", return_value=99)

    asyncio.run(manager._handle_priority(_request(requeue_if_not_scheduled=False)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_BLOCKED


def test_a_self_cancelling_request_is_recorded(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    former = _request()
    former_task = mocker.Mock()
    former.task = former_task
    manager.running_tasks[former.identifier] = former

    manager._handle_duplicate_request(_request(cancels_itself=True))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_SELF_CANCELLED
    former_task.cancel.assert_called_once()


def test_cancelling_another_task_names_both_sides(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    victim = _request(identifier="Rotation(Other)")
    victim_task = mocker.Mock()
    victim.task = victim_task
    manager.running_tasks[victim.identifier] = victim
    canceller = _request(
        identifier="MobsHitting(Tester)",
        cancel_tasks=["Rotation(Other)"],
        correlation_id="decision-2",
    )

    async def _run() -> None:
        await manager._schedule_task(canceller)
        assert canceller.task is not None
        await canceller.task

    asyncio.run(_run())

    # The canceller's own task finishes too, so pick its dispatch record out.
    [call] = [
        c for c in manager.emitted.call_args_list if c.args[1] == ACTION_CANCELS_OTHER
    ]
    correlation_id, event_type, payload = call.args[:3]
    assert correlation_id == "decision-2"
    assert event_type == ACTION_CANCELS_OTHER
    assert payload == {
        "identifier": "MobsHitting(Tester)",
        "cancelled": "Rotation(Other)",
    }
    victim_task.cancel.assert_called_once()


# --- visibility is no longer a per-request dial ---------------------------


def test_an_action_request_carries_no_visibility_flag() -> None:
    """
    `log` gated the text logs these records replace. Capture is total, so a flag
    that could suppress a record would reintroduce exactly the severity/visibility
    conflation ADR-0001 removes.
    """
    assert not hasattr(_request(), "log")


# --- how a scheduled task ended -------------------------------------------


def _finished(manager: _SpiedManager) -> list[tuple[Any, Any]]:
    """
    :return: Every `action.finished` record emitted so far, as
        `(correlation_id, payload)` pairs.
    """
    return [
        (call.args[0], call.args[2])
        for call in manager.emitted.call_args_list
        if call.args[1] == ACTION_FINISHED
    ]


async def _forever() -> None:
    await asyncio.Event().wait()


async def _raise() -> None:
    raise ValueError("boom")


async def _schedule_and_settle(
    manager: _SpiedManager, request: ActionRequest, *, cancel: bool = False
) -> None:
    """
    Schedule the request, optionally cancel its task, and wait until its
    done-callbacks have run.
    """
    await manager._schedule_task(request)
    task = request.task
    assert task is not None
    await asyncio.sleep(0)
    if cancel:
        task.cancel()
    await asyncio.wait([task])
    await asyncio.sleep(0)


def test_a_completed_task_is_finished_once(manager: _SpiedManager) -> None:
    request = _request(correlation_id="decision-3")

    asyncio.run(_schedule_and_settle(manager, request))

    [(correlation_id, payload)] = _finished(manager)
    assert correlation_id == "decision-3"
    assert payload["identifier"] == "Rotation(Tester)"
    assert payload["outcome"] == "completed"
    assert type(payload["elapsed_ms"]) is int


def test_a_cancelled_task_is_finished_once(manager: _SpiedManager) -> None:
    request = ActionRequest("Rotation(Tester)", _forever, "Tester")

    asyncio.run(_schedule_and_settle(manager, request, cancel=True))

    [(_, payload)] = _finished(manager)
    assert payload["outcome"] == "cancelled"


def test_a_raising_task_is_finished_once_and_recorded_as_the_failure(
    manager: _SpiedManager,
) -> None:
    """
    `failure` is how the Session learns it ended in error: the Task Manager turns
    a failing task into a normal return, so nothing else carries the exception.
    """
    request = ActionRequest("Rotation(Tester)", _raise, "Tester")

    asyncio.run(_schedule_and_settle(manager, request))

    [(_, payload)] = _finished(manager)
    assert payload["outcome"] == "raised"
    assert isinstance(manager.failure, ValueError)
    assert manager.queue.get_nowait() is None


def test_elapsed_ms_runs_from_task_creation_to_its_end(
    manager: _SpiedManager, mocker: MockerFixture
) -> None:
    clock = mocker.patch("botting.core.async_task_manager.time")
    clock.monotonic.side_effect = [10.0, 10.25]

    asyncio.run(_schedule_and_settle(manager, _request()))

    [(_, payload)] = _finished(manager)
    assert payload["elapsed_ms"] == 250


def test_a_superseded_task_reports_its_own_request(manager: _SpiedManager) -> None:
    """
    A self-cancelling request reuses its predecessor's name, and is scheduled
    before the predecessor's done-callback runs. Each task still finishes once,
    under its own Correlation ID.
    """
    former = ActionRequest(
        "Rotation(Tester)", _forever, "Tester", correlation_id="decision-old"
    )
    latter = _request(cancels_itself=True, correlation_id="decision-new")

    async def _run() -> None:
        await manager._schedule_task(former)
        await asyncio.sleep(0)
        await manager._process_request(latter)
        assert former.task is not None
        assert latter.task is not None
        await asyncio.wait([former.task, latter.task])
        await asyncio.sleep(0)

    asyncio.run(_run())

    outcomes = {
        correlation_id: (payload["identifier"], payload["outcome"])
        for correlation_id, payload in _finished(manager)
    }
    assert len(_finished(manager)) == 2
    assert outcomes == {
        "decision-old": ("Rotation(Tester)", "cancelled"),
        "decision-new": ("Rotation(Tester)", "completed"),
    }


def test_a_failing_emit_does_not_stop_the_clean_up(manager: _SpiedManager) -> None:
    """Telemetry may never raise inside the thing it observes."""
    manager.emitted.side_effect = RuntimeError("sink is gone")
    request = _request()

    asyncio.run(_schedule_and_settle(manager, request))

    assert request.identifier not in manager.running_tasks
