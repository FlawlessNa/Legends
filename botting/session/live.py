"""
`watch` and `stop`: the reader's commands for a Session that is still running.
They follow `telemetry.jsonl` as it grows, rather than reading it once.

- `watch --until-type GLOB [--count N] [--timeout S]`: waits until N records
  (1 by default) of a matching Event Type are in the file. It counts from the
  start of the file, not from when it was started, so its answer does not
  depend on when the agent began watching. With no `--timeout`, it waits until
  the Session ends.
- `stop [--reason TEXT] [--timeout S]`: writes the stop file
  (`botting.stop_file`), then waits for `session.ended`, 30 s by default. A
  Session that has already ended is left alone: no file is written.

Each prints one line, or one JSON object with `--json`, saying how the wait
ended. Times are on the reader's clock (`reading`): relative to
`session.started`, or to the first record until it arrives.

Exit codes:

- `watch`: 0 the condition was met, 1 timeout, 2 `session.ended` came first.
- `stop`: 0 `session.ended` is in the file, 1 timeout.

Both also exit 1 when there is no Session to read, and 2 on bad arguments
(argparse), as the other commands do; the message on stderr tells them apart.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from fnmatch import fnmatchcase
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from botting.stop_file import request_stop
from botting.telemetry_events import SESSION_ENDED, SESSION_STARTED

from .reading import Record, SessionError, format_time, parse_line, telemetry_path

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The commands this module runs.
COMMANDS: Final = ("watch", "stop")
#: Seconds between two reads of the growing file.
FOLLOW_INTERVAL: Final = 0.2
#: How long `stop` waits for `session.ended` by default, in seconds.
STOP_TIMEOUT: Final = 30.0
#: The reason `stop` writes when none is given.
DEFAULT_REASON: Final = "requested with botting.session stop"


class Follower:
    """
    Reads the records a growing `telemetry.jsonl` has gained since the last
    read, in file order. A line still being written, with no newline yet, waits
    for the next read. Malformed lines are skipped and counted.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.malformed = 0
        self._offset = 0
        self._partial = b""
        self._line = 0
        self._origin: datetime.datetime | None = None
        self._origin_is_start = False

    def new_records(self) -> Iterator[Record]:
        """Every whole record written since the last call."""
        with self.path.open("rb") as handle:
            handle.seek(self._offset)
            chunk = handle.read()
        self._offset += len(chunk)
        *lines, self._partial = (self._partial + chunk).split(b"\n")
        for raw in lines:
            self._line += 1
            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                continue
            record = parse_line(self._line, text)
            if record is None:
                self.malformed += 1
                continue
            yield self._timed(record)

    def _timed(self, record: Record) -> Record:
        """The record with its time on the reader's clock, as far as it is known."""
        if record.event_type == SESSION_STARTED and not self._origin_is_start:
            self._origin, self._origin_is_start = record.timestamp, True
        elif self._origin is None:
            self._origin = record.timestamp
        t = (record.timestamp - self._origin).total_seconds()
        return Record(
            record.line,
            record.timestamp,
            record.correlation_id,
            record.logger_name,
            record.event_type,
            record.payload,
            t,
        )


def run(arguments: argparse.Namespace) -> int:
    """Runs `watch` or `stop`. Returns the exit code."""
    try:
        path = telemetry_path(arguments.dir)
    except SessionError as e:
        _err(f"error: {e}")
        return 1
    follower = Follower(path)
    if arguments.command == "watch":
        code = _watch(follower, arguments)
    else:
        code = _stop(follower, arguments)
    if follower.malformed:
        _err(f"malformed lines: {follower.malformed}")
    return code


# --- Commands ---------------------------------------------------------------------


def _watch(follower: Follower, arguments: argparse.Namespace) -> int:
    pattern: str = arguments.until_type
    count: int = arguments.count
    timeout: float | None = arguments.timeout
    deadline = None if timeout is None else time.monotonic() + timeout
    matched = 0
    while True:
        for record in follower.new_records():
            if fnmatchcase(record.event_type, pattern):
                matched += 1
                if matched >= count:
                    return _report(arguments, "met", 0, matched, count, record)
            if record.event_type == SESSION_ENDED:
                return _report(arguments, "ended", 2, matched, count, record)
        if deadline is not None and time.monotonic() >= deadline:
            return _report(arguments, "timeout", 1, matched, count, None)
        time.sleep(FOLLOW_INTERVAL)


def _stop(follower: Follower, arguments: argparse.Namespace) -> int:
    session_dir = follower.path.parent
    ended = _first_ended(follower)
    if ended is not None:
        _say(arguments, "already_ended", ended, f"already ended: {_ended(ended)}")
        return 0
    stop_file = request_stop(session_dir, arguments.reason)
    deadline = time.monotonic() + arguments.timeout
    while time.monotonic() < deadline:
        time.sleep(FOLLOW_INTERVAL)
        ended = _first_ended(follower)
        if ended is not None:
            _say(arguments, "stopped", ended, f"stopped: {_ended(ended)}")
            return 0
    _say(
        arguments,
        "timeout",
        None,
        f"timeout: no {SESSION_ENDED} after {arguments.timeout:g} s"
        f" ({stop_file} is written)",
    )
    return 1


def _first_ended(follower: Follower) -> Record | None:
    return next(
        (r for r in follower.new_records() if r.event_type == SESSION_ENDED), None
    )


# --- Output -----------------------------------------------------------------------

Result = Literal["met", "ended", "timeout"]


def _report(
    arguments: argparse.Namespace,
    result: Result,
    code: int,
    matched: int,
    count: int,
    record: Record | None,
) -> int:
    """`watch`'s one line: how it ended, and how many matching records it saw."""
    progress = f"{matched} of {count} {arguments.until_type}"
    match result:
        case "met":
            assert record is not None, "the condition is met by a record"
            text = f"met: {progress}, the last at {format_time(record.t)}"
        case "ended":
            assert record is not None, "the Session ends with a record"
            text = f"ended first: {_ended(record)}, with {progress}"
        case "timeout":
            text = f"timeout: {progress} after {arguments.timeout:g} s"
    _say(arguments, result, record, text, matched=matched, count=count)
    return code


def _ended(record: Record) -> str:
    """`session.ended` in words: its cause, its time, and its error if any."""
    cause = record.payload.get("cause")
    error = record.payload.get("error")
    text = f"{cause} at {format_time(record.t)}"
    return f"{text}: {error}" if error else text


def _say(
    arguments: argparse.Namespace,
    result: str,
    record: Record | None,
    text: str,
    **extra: object,
) -> None:
    if not arguments.json:
        sys.stdout.write(text + "\n")
        return
    obj: dict[str, object] = {"result": result, **extra}
    obj["record"] = None if record is None else record.envelope()
    sys.stdout.write(json.dumps(obj) + "\n")


def _err(text: str) -> None:
    sys.stderr.write(text + "\n")


# --- Arguments --------------------------------------------------------------------


def add_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],  # pyright: ignore[reportPrivateUsage]
    common: argparse.ArgumentParser,
) -> None:
    """Adds `watch` and `stop` to the reader's subcommands."""
    watch = commands.add_parser(
        "watch",
        parents=[common],
        help="wait until N records of an Event Type are in the file",
    )
    watch.add_argument(
        "--until-type", required=True, metavar="GLOB", help="Event Type glob"
    )
    watch.add_argument(
        "--count", type=_positive, default=1, metavar="N", help="default: 1"
    )
    watch.add_argument(
        "--timeout",
        type=_seconds,
        metavar="S",
        help="give up after S seconds (default: wait until the Session ends)",
    )

    stop = commands.add_parser(
        "stop", parents=[common], help="ask the Session to stop, and wait until it has"
    )
    stop.add_argument(
        "--reason",
        default=DEFAULT_REASON,
        metavar="TEXT",
        help="recorded in session.stop_requested",
    )
    stop.add_argument(
        "--timeout",
        type=_seconds,
        default=STOP_TIMEOUT,
        metavar="S",
        help=f"seconds to wait for session.ended (default: {STOP_TIMEOUT:g})",
    )


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text} is not a positive count")
    return value


def _seconds(text: str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text} is not a number of seconds")
    return value
