"""
The Telemetry Record stream.

A Telemetry Record is one JSONL line - ``{timestamp, correlation_id,
logger_name, event_type, payload}`` - describing what the bot decided and why.
It is not a log line: text logs carry narrative, Telemetry Records carry
structure meant for an offline analyzer.

Records ride the *existing* logging transport rather than a second queue of
their own. ``emit_event()`` builds an ordinary ``LogRecord`` and hands it to the
logger hierarchy, so a record emitted in an Engine reaches Main Process through
the ``QueueHandler``/``QueueListener`` pair already in place. What separates a
Telemetry Record from a log line is a marker attribute on the record:
``TelemetryHandler`` admits only records that carry it, and ``not_telemetry``
keeps them off every text handler.

The envelope is serialised **at emit time, in the producing process**. That
buys three things at once: the timestamp is the moment of the decision rather
than whenever the listener drained the queue; the record is picklable across
the process boundary no matter what the payload held; and the sink has nothing
left to do but write a line.
"""

from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .logging_config import PARENT_LOG

#: Attribute carrying the serialised envelope on a telemetry ``LogRecord``.
#: Its presence - not its value - is what marks the record as telemetry.
TELEMETRY_ATTR: Final = "telemetry_line"

#: Name of the JSONL file inside the Session directory.
TELEMETRY_FILENAME: Final = "telemetry.jsonl"

#: Logger a Telemetry Record is attributed to when its Producer names none.
DEFAULT_LOGGER_NAME: Final = f"{PARENT_LOG}.telemetry"

#: Telemetry is capture-always and bypasses level checks entirely (see
#: ``emit_event``). A level is carried only because ``LogRecord`` requires one,
#: and it is the quietest available so that a text handler somehow seeing one
#: never raises the console's alarm.
TELEMETRY_LEVEL: Final = logging.DEBUG


def is_telemetry(record: logging.LogRecord) -> bool:
    """
    :return: Whether this record is a Telemetry Record.
    """
    return hasattr(record, TELEMETRY_ATTR)


def not_telemetry(record: logging.LogRecord) -> bool:
    """
    Handler filter keeping Telemetry Records out of the text sinks.

    Every text handler needs it. A Telemetry Record carries an empty message, so
    a handler without this filter contributes one blank line per emitted event
    to its log file - or to the console.

    :return: Whether this record belongs in a text log.
    """
    return not is_telemetry(record)


def _encode(envelope: dict[str, Any]) -> str:
    """
    Serialise an envelope to a single JSON line.

    Payloads come from call sites that are describing a decision, not preparing
    a wire format, so they routinely hold numpy scalars, ``Box`` instances and
    the like. Anything JSON cannot represent is rendered with ``repr()``: a
    lossy field is worth more to the analyzer than a lost record, and telemetry
    must never be able to take down the thing it is observing.

    :param envelope: The five-field Telemetry Record envelope.
    :return: One line of JSON, without its trailing newline.
    """
    try:
        return json.dumps(envelope, default=repr)
    except (TypeError, ValueError) as exc:
        # `default` covers unserialisable *values*; unserialisable dict *keys*
        # and reference cycles still land here. Keep the envelope and degrade
        # only the payload, so the record still correlates.
        degraded = dict(envelope)
        degraded["payload"] = {
            "telemetry_encode_error": repr(exc),
            "payload_repr": repr(envelope.get("payload")),
        }
        return json.dumps(degraded, default=repr)


def emit_event(
    correlation_id: str | None,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    logger_name: str | None = None,
) -> None:
    """
    Emit one Telemetry Record, from any process.

    :param correlation_id: The Correlation ID of the ``_decide()`` call that
        caused this record, or ``None`` when no decision did - Session startup,
        listener lifecycle. Never synthesised: a record that correlates nothing
        says so rather than carrying an id that ties it to nothing.
    :param event_type: What happened. The taxonomy is a separate decision; any
        string is accepted until it lands.
    :param payload: Any Mapping - a `TypedDict` from a `telemetry_events`
        module is the intended shape, and `dict` invariance would reject one.
        Event-specific detail. Defaults to an empty object.
    :param logger_name: The Producer's logger name. Recorded in the envelope and
        used for routing, so pass the Producer's own logger name to keep the
        record attributable; ``DecisionMaker.emit()`` does this for you.
    """
    name = logger_name or DEFAULT_LOGGER_NAME
    logger = logging.getLogger(name)
    record = logger.makeRecord(name, TELEMETRY_LEVEL, "(telemetry)", 0, "", (), None)
    envelope = {
        "timestamp": datetime.datetime.fromtimestamp(record.created)
        .astimezone()
        .isoformat(),
        "correlation_id": correlation_id,
        "logger_name": name,
        "event_type": event_type,
        "payload": {} if payload is None else payload,
    }
    setattr(record, TELEMETRY_ATTR, _encode(envelope))
    # handle() rather than logger.log(): capture is total. A Telemetry Record
    # must not be suppressible by whatever level a logger happens to carry,
    # because its level is a property of the transport, not of the event.
    logger.handle(record)


class TelemetryHandler(logging.Handler):
    """
    The JSONL sink: one Telemetry Record per line, in the Session directory.

    Filters on the marker itself rather than trusting whoever wires it up, so
    attaching it to a logger can never contaminate the stream with text-log
    records.

    Deliberately *unrotated*, unlike the text handlers. An analyzer reads one
    Session's stream as one file, and a rotation boundary mid-Session would
    split a decision chain across two of them.
    """

    def __init__(self, path: Path | str) -> None:
        """
        :param path: The JSONL file to append to. Its parent must already exist.
        """
        super().__init__(level=logging.NOTSET)
        self.path = Path(path)
        self.addFilter(is_telemetry)
        # Line-buffered: a Session that dies mid-decision still leaves every
        # record it emitted up to that point on disk, which is exactly the
        # Session whose telemetry is worth reading.
        self._stream = self.path.open("a", encoding="utf-8", buffering=1)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._stream.write(f"{getattr(record, TELEMETRY_ATTR)}\n")
        except Exception:  # noqa: BLE001 - logging never propagates to the caller
            self.handleError(record)

    def close(self) -> None:
        try:
            if not self._stream.closed:
                self._stream.close()
        finally:
            super().close()
