"""
Reading one Session's ``telemetry.jsonl`` back: the records, the clock, the
filters and the summary the command line prints.

It reads only the ADR 0001 envelope, ``{timestamp, correlation_id,
logger_name, event_type, payload}``. Three Event Types mean something here, and
no others: ``session.started`` sets the clock and names the Bots,
``session.ended`` says how the Session ended, and ``action.finished`` gives the
outcomes per identifier. Everything else is counted and filtered by name only.

**The clock.** Every time is seconds relative to the *origin*: the
``session.started`` record, or the earliest record when there is none. Records
can come before ``session.started``: a process started in
``SessionManager.__enter__`` (the Peripherals process) runs before ``launch``
emits it. Those records get a negative time, ``-00:00.4``, and a time argument
takes a minus sign to reach them. They are counted in the summary rather than
hidden, because the origin is a convention, not a boundary.

**The order.** Records are sorted by timestamp, file order breaking ties. The
file is in the order Main Process *wrote* the records, and a record from an
Engine reaches it through a queue, so file order can lag the clock. The
timestamp is the moment the record was emitted, which is what a time filter
means.

**Damage is counted, never fatal.** A line that isn't a JSON object with the
five envelope fields is *malformed*: skipped, counted and reported by line
number. A record whose payload the sink had to degrade
(``telemetry._encode``) is *degraded*: it is kept, since its envelope still
correlates, and it is counted too. A blank line is neither.
"""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Final

from botting.logging_config import LOGS_ROOT
from botting.telemetry import TELEMETRY_FILENAME
from botting.telemetry_events import ACTION_FINISHED, SESSION_ENDED, SESSION_STARTED

#: The envelope's fields, as ``emit_event`` writes them.
ENVELOPE_FIELDS: Final = (
    "timestamp",
    "correlation_id",
    "logger_name",
    "event_type",
    "payload",
)

#: The payload key ``telemetry._encode`` writes when it had to degrade one.
DEGRADED_KEY: Final = "telemetry_encode_error"

#: How many line numbers a report lists before it only counts them.
SHOWN_LINES: Final = 10


class SessionError(Exception):
    """No Session to read: no directory, or no ``telemetry.jsonl`` in it."""


@dataclass(frozen=True, slots=True)
class Record:
    """One Telemetry Record, with where it sits in the file and on the clock."""

    #: The line number in ``telemetry.jsonl``, from 1.
    line: int
    timestamp: datetime.datetime
    correlation_id: str | None
    logger_name: str
    event_type: str
    payload: Mapping[str, Any]
    #: Seconds since the Session's origin; negative before ``session.started``.
    t: float = 0.0

    @property
    def degraded(self) -> bool:
        """Whether the sink replaced this record's payload with a repr."""
        return DEGRADED_KEY in self.payload

    def envelope(self) -> dict[str, Any]:
        """The record as it was written, plus its line and its time."""
        return {
            "t": round(self.t, 3),
            "line": self.line,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "logger_name": self.logger_name,
            "event_type": self.event_type,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class Session:
    """One Session's records, in time order, and what could not be read."""

    path: Path
    records: Sequence[Record]
    #: The origin's timestamp, or ``None`` when there are no records.
    origin: datetime.datetime | None
    #: ``session.started`` or ``first record``, or ``None`` with no records.
    origin_from: str | None
    malformed_lines: Sequence[int] = field(default_factory=tuple)

    @property
    def degraded_lines(self) -> list[int]:
        """The line numbers of every degraded record, in file order."""
        return sorted(record.line for record in self.records if record.degraded)

    def first(self, event_type: str) -> Record | None:
        """The earliest record of one Event Type, if any."""
        return next((r for r in self.records if r.event_type == event_type), None)

    def resolve(self, time: TimeArg) -> float:
        """A time argument, as seconds on this Session's clock."""
        if time.at is None:
            return time.seconds
        if self.origin is None:
            # No records: nothing will match, wherever the time lands.
            return 0.0
        return (time.at - self.origin).total_seconds()


# --- Finding and loading ----------------------------------------------------------


def latest_session_dir(root: Path | None = None) -> Path:
    """
    The newest Session directory under ``root`` that has a ``telemetry.jsonl``,
    finished or still running.

    Directory names are ``YYYY-MM-DD_HH-MM-SS`` (``new_session_dir``), so name
    order is age order, as ``prune_old_sessions`` relies on too.

    :param root: Where Session directories are; ``logs/`` by default.
    :raises SessionError: when there is none.
    """
    root = LOGS_ROOT if root is None else root
    candidates = (
        sorted(
            (p for p in root.iterdir() if (p / TELEMETRY_FILENAME).is_file()),
            key=lambda p: p.name,
        )
        if root.is_dir()
        else []
    )
    if not candidates:
        raise SessionError(f"no directory under {root} has a {TELEMETRY_FILENAME}")
    return candidates[-1]


def telemetry_path(target: Path | None, root: Path | None = None) -> Path:
    """
    The ``telemetry.jsonl`` to read: in ``target``, ``target`` itself when it is
    the file, or in the newest Session under ``root`` when ``target`` is ``None``.

    :raises SessionError: when it does not exist.
    """
    if target is None:
        return latest_session_dir(root) / TELEMETRY_FILENAME
    path = target if target.is_file() else target / TELEMETRY_FILENAME
    if not path.is_file():
        raise SessionError(f"{target} has no {TELEMETRY_FILENAME}")
    return path


def load_session(path: Path) -> Session:
    """Read one ``telemetry.jsonl``. Damage is counted, never raised."""
    parsed: list[Record] = []
    malformed: list[int] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = parse_line(number, line)
            if record is None:
                malformed.append(number)
            else:
                parsed.append(record)
    # Stable: records with the same timestamp keep their file order.
    parsed.sort(key=lambda r: r.timestamp)

    started = next((r for r in parsed if r.event_type == SESSION_STARTED), None)
    if started is not None:
        origin, origin_from = started.timestamp, SESSION_STARTED
    elif parsed:
        origin, origin_from = parsed[0].timestamp, "first record"
    else:
        origin, origin_from = None, None
    records = [
        r if origin is None else _with_time(r, (r.timestamp - origin).total_seconds())
        for r in parsed
    ]
    return Session(path, records, origin, origin_from, tuple(malformed))


def parse_line(number: int, line: str) -> Record | None:
    """One line as a Record, or ``None`` when it is not a whole envelope."""
    try:
        raw = json.loads(line)
    except ValueError:
        return None
    if not isinstance(raw, dict) or any(key not in raw for key in ENVELOPE_FIELDS):
        return None
    timestamp, cid, logger_name, event_type, payload = (
        raw[key] for key in ENVELOPE_FIELDS
    )
    if not (
        isinstance(timestamp, str)
        and isinstance(event_type, str)
        and isinstance(logger_name, str)
        and isinstance(payload, dict)
        and (cid is None or isinstance(cid, str))
    ):
        return None
    try:
        moment = datetime.datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    # `emit_event` always writes an offset. A naive one is read as local time,
    # which is what the writer meant, so it still compares with the rest.
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return Record(number, moment, cid, logger_name, event_type, payload)


def _with_time(record: Record, t: float) -> Record:
    return Record(
        record.line,
        record.timestamp,
        record.correlation_id,
        record.logger_name,
        record.event_type,
        record.payload,
        t,
    )


# --- Times ------------------------------------------------------------------------

_CLOCK = re.compile(r"(?P<sign>[+-])(?P<minutes>\d+):(?P<seconds>\d{1,2}(?:\.\d+)?)")
_SECONDS = re.compile(r"[+-]?\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class TimeArg:
    """
    A time from the command line: either relative seconds, or a wall-clock
    moment that a Session turns into seconds (``Session.resolve``).
    """

    seconds: float = 0.0
    at: datetime.datetime | None = None


def parse_time(text: str) -> TimeArg:
    """
    Read ``+mm:ss[.s]`` (or ``-mm:ss[.s]``, before ``session.started``), plain
    seconds such as ``97.5`` or ``-0.4``, or an ISO-8601 timestamp. A timestamp
    without an offset is local time, as the records are.

    The sign is required on ``mm:ss``, so ``21:14`` is never silently read as
    21 minutes when a wall-clock time was meant: write ``+21:14`` or a full
    timestamp.

    :raises ValueError: for anything else, with a message saying what is
        accepted.
    """
    text = text.strip()
    if clock := _CLOCK.fullmatch(text):
        seconds = float(clock["seconds"])
        if seconds >= 60:
            raise ValueError(f"{text!r}: seconds must be below 60")
        total = int(clock["minutes"]) * 60 + seconds
        return TimeArg(seconds=-total if clock["sign"] == "-" else total)
    if _SECONDS.fullmatch(text):
        return TimeArg(seconds=float(text))
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"{text!r} is not a time: use +mm:ss[.s], seconds (97.5), "
            "or an ISO-8601 timestamp"
        ) from None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return TimeArg(at=moment)


def format_time(t: float, *, signed: bool = True) -> str:
    """
    Seconds as ``+mm:ss.s``, or ``-mm:ss.s`` before the origin; a duration
    passes ``signed=False`` and reads ``mm:ss.s``.
    """
    tenths = round(abs(t) * 10)
    sign = "-" if t < 0 and tenths else "+" if signed else ""
    minutes, tenths = divmod(tenths, 600)
    return f"{sign}{minutes:02d}:{tenths // 10:02d}.{tenths % 10}"


# --- Filtering --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Where:
    """One ``key=GLOB`` condition on a payload field."""

    key: str
    pattern: str

    def matches(self, payload: Mapping[str, Any]) -> bool:
        """
        Whether the field matches. A dotted key reaches into nested objects. A
        string is matched as it is; any other value as its JSON (``1``,
        ``true``, ``null``). A missing field never matches.
        """
        value: Any = payload
        for part in self.key.split("."):
            if not isinstance(value, Mapping) or part not in value:
                return False
            value = value[part]
        text = value if isinstance(value, str) else json.dumps(value)
        return fnmatchcase(text, self.pattern)


def parse_where(text: str) -> Where:
    """
    Read ``key=GLOB``. The first ``=`` splits it, so the glob may hold more.

    :raises ValueError: when there is no ``=`` or no key.
    """
    key, equals, pattern = text.partition("=")
    if not equals or not key:
        raise ValueError(f"{text!r} is not key=GLOB")
    return Where(key, pattern)


def select(
    records: Iterable[Record],
    *,
    event_type: str = "*",
    where: Sequence[Where] = (),
    since: float | None = None,
    until: float | None = None,
) -> list[Record]:
    """The records matching every condition given; bounds are inclusive."""
    return [
        r
        for r in records
        if fnmatchcase(r.event_type, event_type)
        and (since is None or r.t >= since)
        and (until is None or r.t <= until)
        and all(condition.matches(r.payload) for condition in where)
    ]


# --- Summary ----------------------------------------------------------------------


def summarize(session: Session) -> dict[str, Any]:
    """
    Everything ``summary`` prints, as one JSON-ready object. Its size grows with
    the number of Event Types, Bots and action identifiers, never with the
    number of records.
    """
    records = session.records
    started = session.first(SESSION_STARTED)
    ended = session.first(SESSION_ENDED)
    last_t = max((r.t for r in records), default=0.0)

    actions: dict[str, Counter[str]] = {}
    for record in records:
        if record.event_type == ACTION_FINISHED:
            identifier = str(record.payload.get("identifier"))
            outcome = str(record.payload.get("outcome"))
            actions.setdefault(identifier, Counter())[outcome] += 1

    event_types = Counter(r.event_type for r in records)
    degraded = session.degraded_lines
    return {
        "path": str(session.path),
        "origin": session.origin.isoformat() if session.origin else None,
        "origin_from": session.origin_from,
        "duration_s": round(ended.t if ended else last_t, 3),
        "records": len(records),
        "before_origin": sum(1 for r in records if r.t < 0),
        "first_t": round(records[0].t, 3) if records else None,
        "malformed": _damage(session.malformed_lines),
        "degraded": _damage(degraded),
        "bots": _bots(started),
        "debug": started.payload.get("debug") if started else None,
        "event_types": dict(
            sorted(event_types.items(), key=lambda kv: (-kv[1], kv[0]))
        ),
        "actions": {
            identifier: dict(sorted(outcomes.items()))
            for identifier, outcomes in sorted(actions.items())
        },
        "ended": None
        if ended is None
        else {
            "t": round(ended.t, 3),
            "cause": ended.payload.get("cause"),
            "error": ended.payload.get("error"),
        },
    }


def _damage(lines: Sequence[int]) -> dict[str, Any]:
    return {"count": len(lines), "lines": list(lines[:SHOWN_LINES])}


def _bots(started: Record | None) -> list[dict[str, Any]] | None:
    """``session.started``'s Bots, keeping only what has the expected shape."""
    if started is None:
        return None
    bots = started.payload.get("bots")
    if not isinstance(bots, list):
        return []
    return [
        {
            "ign": bot.get("ign"),
            "bot_class": bot.get("bot_class"),
            "decision_makers": names if isinstance(names, list) else [],
        }
        for bot in bots
        if isinstance(bot, dict)
        for names in [bot.get("decision_makers")]
    ]
