"""
One structured question to a language model, answered with a value.

The bot's only use of a model is "here are instructions and a conversation,
fill in this schema". ``StructuredModel.ask`` is that question, and it **always
returns**: an answer, a refusal, a timeout or an error, as a ``ModelAnswer``.
It never raises, because the caller is a DecisionMaker that must keep running
whatever the network does.

This module knows nothing about MapleStory. Credentials are the SDK's own
resolution (``ANTHROPIC_API_KEY``, or an ``ant auth login`` profile): nothing
is read from a config file here, and no key belongs in the repository.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Final, Literal, Protocol

import anthropic
from pydantic import BaseModel

from .telemetry import emit_event
from .telemetry_events import LLM_REQUEST, LlmRequestPayload

logger = logging.getLogger(__name__)

Outcome = Literal["ok", "refused", "timeout", "error"]
Effort = Literal["low", "medium", "high", "xhigh", "max"]

DEFAULT_MODEL_ID: Final = "claude-haiku-5-5"
DEFAULT_EFFORT: Final[Effort] = "low"
DEFAULT_TIMEOUT_S: Final = 10.0
DEFAULT_MAX_RETRIES: Final = 2
MAX_TOKENS: Final = 1024


@dataclass(frozen=True)
class ModelAnswer:
    """
    What a request came to.

    :param outcome: ``ok``, ``refused``, ``timeout`` or ``error``.
    :param value: The parsed schema instance. Set only when ``outcome`` is
        ``ok``.
    :param detail: Names the cause when ``outcome`` is not ``ok``, else empty.
    :param ms: Wall-clock latency of the whole call, retries included.
    """

    outcome: Outcome
    value: BaseModel | None
    detail: str
    ms: int


class StructuredModel(Protocol):
    """Anything that can answer one structured question."""

    async def ask(
        self, system: str, user: str, schema: type[BaseModel]
    ) -> ModelAnswer: ...


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class AnthropicModel:
    """
    ``StructuredModel`` backed by the Anthropic Messages API.

    The system prompt is sent with ``cache_control`` so the fixed instructions
    are cached across calls. The SDK's own retries (``max_retries``) run before
    a failure is reported.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        effort: Effort = DEFAULT_EFFORT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.model_id = model_id
        self.effort: Effort = effort
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._client = anthropic.AsyncAnthropic(
            timeout=timeout_s, max_retries=max_retries
        )

    async def ask(self, system: str, user: str, schema: type[BaseModel]) -> ModelAnswer:
        """
        Ask one question. Never raises.

        ``messages.create`` with the schema as ``output_config`` format, rather
        than ``messages.parse``: parse validates before the caller can read
        ``stop_reason``, so a refusal carrying an empty text block would be an
        error instead of ``refused``.

        :param system: The fixed instructions. Cached.
        :param user: The question, including the conversation so far.
        :param schema: The shape of the answer.
        """
        start = time.perf_counter()
        usage: anthropic.types.Usage | None = None
        value: BaseModel | None = None
        outcome: Outcome
        detail = ""
        try:
            message = await self._client.messages.create(
                model=self.model_id,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": self.effort,
                    "format": {
                        "type": "json_schema",
                        "schema": anthropic.transform_schema(schema),
                    },
                },
            )
            usage = message.usage
            if message.stop_reason == "refusal":
                outcome, detail = "refused", "stop_reason is refusal"
            else:
                text = "".join(
                    block.text for block in message.content if block.type == "text"
                )
                value = schema.model_validate_json(text)
                outcome = "ok"
        except anthropic.APITimeoutError as exc:
            outcome, detail = "timeout", _describe(exc)
        except Exception as exc:  # noqa: BLE001 - the contract is "never raises"
            outcome, detail = "error", _describe(exc)

        ms = int((time.perf_counter() - start) * 1000)
        self._record(usage, ms, outcome)
        return ModelAnswer(outcome=outcome, value=value, detail=detail, ms=ms)

    async def check(self) -> str | None:
        """
        Whether the model can be reached with the credentials at hand.

        :return: ``None`` when it can, else the cause, for a startup refusal.
        """
        try:
            await self._client.models.retrieve(self.model_id)
        except Exception as exc:  # noqa: BLE001 - the cause is the return value
            return _describe(exc)
        return None

    def _record(
        self, usage: anthropic.types.Usage | None, ms: int, outcome: Outcome
    ) -> None:
        """Emit ``llm.request``. Telemetry may never raise inside the caller."""
        try:
            payload = LlmRequestPayload(
                model=self.model_id,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                cached_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                ms=ms,
                outcome=outcome,
            )
            emit_event(None, LLM_REQUEST, payload, logger.name)
        except Exception:
            logger.debug("llm.request telemetry failed", exc_info=True)
