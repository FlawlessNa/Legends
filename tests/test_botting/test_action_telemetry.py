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

import pytest

from botting.core.action_data import ActionRequest
from botting.core.async_task_manager import AsyncTaskManager
from botting.telemetry_events import (
    ACTION_BLOCKED,
    ACTION_CANCELS_OTHER,
    ACTION_REQUEUED,
    ACTION_SCHEDULED,
    ACTION_SELF_CANCELLED,
)


async def _noop() -> None:
    """The procedure a scheduled request runs. Nothing here touches a client."""


def _request(identifier="Rotation(Tester)", **kwargs) -> ActionRequest:
    return ActionRequest(identifier, _noop, "Tester", **kwargs)


@pytest.fixture
def manager(mocker):
    """
    :return: An AsyncTaskManager whose `emit_event` is a spy, exposed as
        `manager.emitted`.
    """
    manager = AsyncTaskManager(mocker.Mock())
    manager.emitted = mocker.patch("botting.core.async_task_manager.emit_event")
    return manager


def _only_call(manager):
    args, _ = manager.emitted.call_args
    correlation_id, event_type, payload = args[:3]
    return correlation_id, event_type, payload


# --- the envelope a dispatch record carries -------------------------------


def test_the_record_carries_the_requests_correlation_id(manager):
    request = _request(correlation_id="decision-1", priority=7)

    manager._emit(ACTION_SCHEDULED, request)

    correlation_id, event_type, payload = _only_call(manager)
    assert correlation_id == "decision-1"
    assert event_type == ACTION_SCHEDULED
    assert payload == {"identifier": "Rotation(Tester)", "priority": 7}


def test_a_request_no_decision_caused_correlates_nothing(manager):
    """
    Null rather than a synthesised id: a record that ties to no decision says so.
    """
    manager._emit(ACTION_SCHEDULED, _request())

    correlation_id, _, _ = _only_call(manager)
    assert correlation_id is None


def test_the_priority_is_a_builtin_int(manager):
    """Payloads carry JSON primitives, converted at the call site."""
    manager._emit(ACTION_SCHEDULED, _request(priority=3))

    _, _, payload = _only_call(manager)
    assert type(payload["priority"]) is int


# --- one record per disposal ----------------------------------------------


def test_a_scheduled_request_is_recorded(manager, mocker):
    mocker.patch.object(manager, "_schedule_task", mocker.AsyncMock())

    asyncio.run(manager._handle_priority(_request(priority=5)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_SCHEDULED


def test_a_requeued_request_is_recorded(manager, mocker):
    mocker.patch.object(manager, "_get_priority_blocking", return_value=99)

    asyncio.run(manager._handle_priority(_request(requeue_if_not_scheduled=True)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_REQUEUED


def test_a_blocked_request_is_recorded(manager, mocker):
    """
    The branch a lower-priority request dies in. It is the most analytically
    interesting of the four and the one whose text log was never gated, so it
    would be the easiest to leave behind.
    """
    mocker.patch.object(manager, "_get_priority_blocking", return_value=99)

    asyncio.run(manager._handle_priority(_request(requeue_if_not_scheduled=False)))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_BLOCKED


def test_a_self_cancelling_request_is_recorded(manager, mocker):
    former = _request()
    former.task = mocker.Mock()
    manager.running_tasks[former.identifier] = former

    manager._handle_duplicate_request(_request(cancels_itself=True))

    _, event_type, _ = _only_call(manager)
    assert event_type == ACTION_SELF_CANCELLED
    former.task.cancel.assert_called_once()


def test_cancelling_another_task_names_both_sides(manager, mocker):
    victim = _request(identifier="Rotation(Other)")
    victim.task = mocker.Mock()
    manager.running_tasks[victim.identifier] = victim
    canceller = _request(
        identifier="MobsHitting(Tester)",
        cancel_tasks=["Rotation(Other)"],
        correlation_id="decision-2",
    )

    async def _run() -> None:
        await manager._schedule_task(canceller)
        await canceller.task

    asyncio.run(_run())

    correlation_id, event_type, payload = _only_call(manager)
    assert correlation_id == "decision-2"
    assert event_type == ACTION_CANCELS_OTHER
    assert payload == {
        "identifier": "MobsHitting(Tester)",
        "cancelled": "Rotation(Other)",
    }
    victim.task.cancel.assert_called_once()


# --- visibility is no longer a per-request dial ---------------------------


def test_an_action_request_carries_no_visibility_flag():
    """
    `log` gated the text logs these records replace. Capture is total, so a flag
    that could suppress a record would reintroduce exactly the severity/visibility
    conflation ADR-0001 removes.
    """
    assert not hasattr(_request(), "log")
