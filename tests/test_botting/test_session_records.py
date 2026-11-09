"""
Tests for the `session.*` Telemetry Records that bracket a Session's
`telemetry.jsonl`: what it ran, and why it ended.

`SessionManager` itself spawns a Manager process and configures logging, so the
payloads are built by pure helpers that `launch` and `__exit__` call, and those
are what is tested here.
"""

import asyncio

import pytest
from pytest_mock import MockerFixture

from botting.core.bot import Bot
from botting.core.decision_maker import DecisionMaker
from botting.core.session_manager import (
    _ended_cause,
    _session_ended_payload,
    _session_started_payload,
)


class Rotation(DecisionMaker):  # pyright: ignore[reportImplicitAbstractClass]
    """Named only; never built."""


class Looting(DecisionMaker):  # pyright: ignore[reportImplicitAbstractClass]
    """Named only; never built."""


class _FarmBot(Bot):
    def find_handle(self) -> int:
        raise AssertionError("session.started looks up no window")

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [Rotation, Looting]


class _ChatBot(Bot):
    def find_handle(self) -> int:
        raise AssertionError("session.started looks up no window")

    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return []


@pytest.fixture
def bots(mocker: MockerFixture) -> list[Bot]:
    return [_FarmBot("Farmer", mocker.Mock()), _ChatBot("Chatter", mocker.Mock())]


# --- session.started ------------------------------------------------------


def test_session_started_lists_every_bot_and_its_decision_makers(
    bots: list[Bot],
) -> None:
    """
    Built from the Bots as Main Process holds them: before `child_init`, so
    reaching for the `decision_makers` property would fail on `data is None`.
    """
    assert _session_started_payload(bots, debug=False) == {
        "bots": [
            {
                "ign": "Farmer",
                "bot_class": "_FarmBot",
                "decision_makers": ["Rotation", "Looting"],
            },
            {"ign": "Chatter", "bot_class": "_ChatBot", "decision_makers": []},
        ],
        "debug": False,
    }


def test_session_started_says_whether_the_session_is_in_debug(bots: list[Bot]) -> None:
    assert _session_started_payload(bots, debug=True)["debug"] is True


def test_session_started_does_not_build_the_decision_makers(bots: list[Bot]) -> None:
    _session_started_payload(bots, debug=False)

    assert "decision_makers" not in vars(bots[0])


# --- session.ended: the cause, by precedence ------------------------------


@pytest.mark.parametrize(
    ("stop_reason", "failure", "exc", "cause"),
    [
        pytest.param(
            "tests done",
            ValueError(),
            KeyboardInterrupt(),
            "stop_file",
            id="a stop request beats everything",
        ),
        pytest.param(
            None,
            ValueError(),
            KeyboardInterrupt(),
            "error",
            id="a failing task beats an interrupt",
        ),
        pytest.param(
            None,
            None,
            KeyboardInterrupt(),
            "interrupted",
            id="ctrl+c or a discord kill",
        ),
        pytest.param(
            None, None, asyncio.CancelledError(), "interrupted", id="cancellation"
        ),
        pytest.param(None, None, RuntimeError(), "error", id="any other exception"),
        pytest.param(
            None, ValueError(), None, "error", id="a failing task while launch returned"
        ),
        pytest.param(None, None, None, "completed", id="nothing went wrong"),
    ],
)
def test_the_end_cause_follows_its_precedence(
    stop_reason: str | None,
    failure: BaseException | None,
    exc: BaseException | None,
    cause: str,
) -> None:
    assert _ended_cause(stop_reason, failure, exc) == cause


def test_an_error_names_the_failing_task_before_what_it_caused() -> None:
    payload = _session_ended_payload(
        None, ValueError("bad frame"), RuntimeError("follow-on")
    )

    assert payload == {"cause": "error", "error": "ValueError: bad frame"}


def test_an_error_leaving_the_context_is_named() -> None:
    payload = _session_ended_payload(None, None, RuntimeError("engine died"))

    assert payload == {"cause": "error", "error": "RuntimeError: engine died"}


@pytest.mark.parametrize(
    ("stop_reason", "exc"),
    [("tests done", None), (None, KeyboardInterrupt()), (None, None)],
)
def test_no_error_is_named_unless_the_cause_is_error(
    stop_reason: str | None, exc: BaseException | None
) -> None:
    assert _session_ended_payload(stop_reason, None, exc)["error"] is None
