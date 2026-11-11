"""
Tests for `botting.llm.AnthropicModel`.

The real Anthropic SDK runs end to end: only the HTTP transport is replaced
(an `httpx2.MockTransport`), so request building, response parsing, retries and
the SDK's own error types are the real ones. No test touches the network.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
from pydantic import BaseModel
from pytest_mock import MockerFixture

from botting.llm import AnthropicModel, ModelAnswer, StructuredModel
from botting.telemetry_events import LLM_REQUEST

Handler = Callable[[httpx2.Request], httpx2.Response]


class Reply(BaseModel):
    text: str


def _message(
    *,
    text: str = '{"text": "hi"}',
    stop_reason: str = "end_turn",
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage
        or {
            "input_tokens": 120,
            "output_tokens": 7,
            "cache_read_input_tokens": 100,
            "cache_creation_input_tokens": 0,
        },
    }


def _model(handler: Handler, *, max_retries: int = 0) -> AnthropicModel:
    model = AnthropicModel(max_retries=max_retries)
    model._client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=max_retries,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return model


def _ask(model: AnthropicModel) -> ModelAnswer:
    return asyncio.run(model.ask("be brief", "hello?", Reply))


def test_it_is_a_structured_model() -> None:
    model: StructuredModel = AnthropicModel()
    assert model is not None


def test_defaults() -> None:
    model = AnthropicModel()
    assert (model.model_id, model.effort, model.timeout_s, model.max_retries) == (
        "claude-haiku-5-5",
        "low",
        10.0,
        2,
    )


def test_an_answer_is_parsed_into_the_schema() -> None:
    answer = _ask(_model(lambda r: httpx2.Response(200, json=_message())))
    assert answer.outcome == "ok"
    assert answer.value == Reply(text="hi")
    assert answer.detail == ""
    assert answer.ms >= 0


def test_the_request_is_haiku_low_effort_capped_with_a_cached_system_prompt() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=_message())

    _ask(_model(handler))

    (body,) = seen
    assert body["model"] == "claude-haiku-5-5"
    assert body["max_tokens"] == 1024
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"] == [
        {
            "type": "text",
            "text": "be brief",
            "cache_control": {"type": "ephemeral"},
        }
    ]
    assert body["messages"] == [{"role": "user", "content": "hello?"}]


def test_a_refusal_is_refused_not_raised() -> None:
    body = _message(text="", stop_reason="refusal")
    answer = _ask(_model(lambda r: httpx2.Response(200, json=body)))
    assert answer.outcome == "refused"
    assert answer.value is None


def test_a_timeout_is_timeout_not_raised() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow", request=request)

    answer = _ask(_model(handler))
    assert answer.outcome == "timeout"
    assert answer.value is None
    assert "Timeout" in answer.detail


def test_an_api_error_is_error_not_raised() -> None:
    error = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "bad key"},
    }
    answer = _ask(_model(lambda r: httpx2.Response(401, json=error)))
    assert answer.outcome == "error"
    assert answer.value is None
    assert "AuthenticationError" in answer.detail


def test_a_connection_failure_is_error_not_raised() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no network", request=request)

    answer = _ask(_model(handler))
    assert answer.outcome == "error"
    assert answer.value is None


def test_an_answer_that_does_not_fit_the_schema_is_error_not_raised() -> None:
    body = _message(text='{"wrong": 1}')
    answer = _ask(_model(lambda r: httpx2.Response(200, json=body)))
    assert answer.outcome == "error"
    assert answer.value is None


def test_the_sdk_retries_before_giving_up() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        if len(calls) < 2:
            return httpx2.Response(
                500,
                json={"type": "error", "error": {"type": "api_error", "message": "x"}},
            )
        return httpx2.Response(200, json=_message())

    answer = _ask(_model(handler, max_retries=2))
    assert answer.outcome == "ok"
    assert len(calls) == 2


def test_check_is_none_when_the_model_exists() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/models/claude-haiku-5-5"
        return httpx2.Response(
            200,
            json={
                "id": "claude-haiku-5-5",
                "type": "model",
                "display_name": "Haiku",
                "created_at": "2026-01-01T00:00:00Z",
            },
        )

    assert asyncio.run(_model(handler).check()) is None


def test_check_returns_the_cause_on_failure() -> None:
    error = {
        "type": "error",
        "error": {"type": "authentication_error", "message": "bad key"},
    }
    cause = asyncio.run(_model(lambda r: httpx2.Response(401, json=error)).check())
    assert cause is not None
    assert "AuthenticationError" in cause


def test_each_call_emits_llm_request(mocker: MockerFixture) -> None:
    emitted = mocker.patch("botting.llm.emit_event")
    _ask(_model(lambda r: httpx2.Response(200, json=_message())))

    emitted.assert_called_once()
    _, event_type, payload = emitted.call_args.args[:3]
    assert event_type == LLM_REQUEST
    assert payload["model"] == "claude-haiku-5-5"
    assert payload["input_tokens"] == 120
    assert payload["cached_tokens"] == 100
    assert payload["output_tokens"] == 7
    assert payload["outcome"] == "ok"
    assert payload["ms"] >= 0


def test_a_failed_call_still_emits_llm_request(mocker: MockerFixture) -> None:
    emitted = mocker.patch("botting.llm.emit_event")

    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow", request=request)

    _ask(_model(handler))

    payload = emitted.call_args.args[2]
    assert payload["outcome"] == "timeout"
    assert payload["input_tokens"] == 0


def test_telemetry_failing_never_breaks_the_answer(mocker: MockerFixture) -> None:
    mocker.patch("botting.llm.emit_event", side_effect=RuntimeError("sink gone"))
    answer = _ask(_model(lambda r: httpx2.Response(200, json=_message())))
    assert answer.outcome == "ok"


def test_llm_request_carries_the_correlation_id_of_the_decision_that_asked(
    mocker: MockerFixture,
) -> None:
    emitted = mocker.patch("botting.llm.emit_event")
    model = _model(lambda r: httpx2.Response(200, json=_message()))

    asyncio.run(model.ask("system", "user", Reply, correlation_id="decision-7"))

    assert emitted.call_args.args[:2] == ("decision-7", LLM_REQUEST)
