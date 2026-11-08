"""
`python -m botting.session <command> [DIR]`: the command line, and the only
module in the package that prints.

- `summary`: duration, record count, the Bots and their DecisionMakers, a
  count per Event Type, `action.finished` outcomes per identifier, and how the
  Session ended. A few hundred tokens, whatever the Session's length.
- `events [--type GLOB] [--where KEY=GLOB]... [--since T] [--until T]
  [--limit N]`: the matching records, one per line. `--where` matches a
  payload field; give it more than once and every condition must hold.
- `around --at T [--window S]`: every record within S seconds of T (5 s by
  default).
- `frame --at T [--box l,t,r,b] [--scale F]`: a PNG of the Session's video at T,
  written to `<DIR>/frames/`. `--box` is in screen pixels. Exits 1 when there is
  no recording to cut from.

`DIR` is a Session directory, `logs/<YYYY-MM-DD_HH-MM-SS>/`. Without it, the
newest one with a `telemetry.jsonl` is read, finished or still running. Times
print relative to `session.started` (`+mm:ss.s`), and `T` is `+mm:ss[.s]`,
plain seconds (`97.5`) or an ISO-8601 timestamp; `reading` explains the clock.
`--json` prints one JSON object per line instead of text.

Exit codes: 0 done, 1 no Session (or no recording) to read, 2 bad arguments (argparse).
Malformed lines are reported, on stdout by `summary` and on stderr by the
others, and are never an error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .frames import FrameError, cut_frame, parse_box
from .reading import (
    Record,
    Session,
    SessionError,
    TimeArg,
    format_time,
    load_session,
    parse_time,
    parse_where,
    select,
    summarize,
    telemetry_path,
)

#: `around`'s default half-window, in seconds.
DEFAULT_WINDOW = 5.0


def main(argv: Sequence[str] | None = None) -> int:
    """Runs one command. Returns the exit code: 0, or 1 with no Session."""
    arguments = _parser().parse_args(argv)
    try:
        session = load_session(telemetry_path(arguments.dir))
    except SessionError as e:
        _err(f"error: {e}")
        return 1
    match arguments.command:
        case "summary":
            _summary(session, as_json=arguments.json)
        case "events":
            _events(session, arguments)
        case "frame":
            return _frame(session, arguments)
        case _:
            _around(session, arguments)
    return 0


# --- Commands ---------------------------------------------------------------------


def _summary(session: Session, *, as_json: bool) -> None:
    summary = summarize(session)
    if as_json:
        _out(json.dumps(summary))
        return
    lines = [f"session: {session.path.parent}"]
    if summary["origin"] is None:
        lines.append("records: 0")
    else:
        lines.append(f"origin: {summary['origin']} ({summary['origin_from']})")
        so_far = "" if summary["ended"] else " so far"
        duration = format_time(summary["duration_s"], signed=False)
        lines.append(f"duration: {duration}{so_far}")
        records = f"records: {summary['records']}"
        if summary["before_origin"]:
            records += (
                f" ({summary['before_origin']} before session.started,"
                f" the first at {format_time(summary['first_t'])})"
            )
        lines.append(records)
    lines += _damage_lines(summary)
    lines += _bot_lines(summary)
    if summary["event_types"]:
        lines.append("event types:")
        width = max(map(len, summary["event_types"]))
        lines += [
            f"  {name:<{width}}  {count}"
            for name, count in summary["event_types"].items()
        ]
    if summary["actions"]:
        lines.append("action.finished:")
        width = max(map(len, summary["actions"]))
        for identifier, outcomes in summary["actions"].items():
            counts = "  ".join(f"{k} {v}" for k, v in outcomes.items())
            lines.append(f"  {identifier:<{width}}  {counts}")
    lines.append(_ended_line(summary["ended"]))
    _out("\n".join(lines))


def _events(session: Session, arguments: argparse.Namespace) -> None:
    matches = select(
        session.records,
        event_type=arguments.type,
        where=arguments.where,
        since=_resolve(session, arguments.since),
        until=_resolve(session, arguments.until),
    )
    limit: int | None = arguments.limit
    shown = matches if limit is None else matches[:limit]
    _print_records(shown, as_json=arguments.json)
    if len(shown) < len(matches):
        _err(f"limit reached: {len(shown)} of {len(matches)} matching records shown")
    _report_damage(session)


def _around(session: Session, arguments: argparse.Namespace) -> None:
    at = session.resolve(arguments.at)
    window: float = arguments.window
    nearby = select(session.records, since=at - window, until=at + window)
    if arguments.json:
        _print_records(nearby, as_json=True)
    else:
        before = [r for r in nearby if r.t < at]
        _print_records(before, as_json=False)
        _out(f"---------- {format_time(at)} ----------")
        _print_records(nearby[len(before) :], as_json=False)
    _report_damage(session)


def _frame(session: Session, arguments: argparse.Namespace) -> int:
    at = session.resolve(arguments.at)
    try:
        path, index = cut_frame(session, at, arguments.box, arguments.scale)
    except FrameError as e:
        _err(f"error: {e}")
        return 1
    if arguments.json:
        _out(json.dumps({"path": str(path), "frame_index": index, "t": round(at, 3)}))
    else:
        _out(f"{path}  (frame {index} at {format_time(at)})")
    return 0


# --- Output -----------------------------------------------------------------------


def _print_records(records: Sequence[Record], *, as_json: bool) -> None:
    for record in records:
        _out(json.dumps(record.envelope()) if as_json else _record_line(record))


def _record_line(record: Record) -> str:
    """
    One record as text. The Correlation ID is cut to its first 8 characters,
    which tell a Session's ids apart; `--json` has it whole, and the logger.
    """
    cid = f"  cid={record.correlation_id[:8]}" if record.correlation_id else ""
    payload = json.dumps(dict(record.payload), separators=(",", ":"))
    return f"{format_time(record.t)}  {record.event_type}{cid}  {payload}"


def _damage_lines(summary: dict[str, Any]) -> list[str]:
    lines = []
    for key, what in [
        ("malformed", "malformed lines"),
        ("degraded", "degraded payloads"),
    ]:
        damage = summary[key]
        if damage["count"]:
            lines.append(f"{what}: {damage['count']} {_line_list(damage)}")
    return lines


def _line_list(damage: dict[str, Any]) -> str:
    shown = ", ".join(map(str, damage["lines"]))
    more = ", ..." if damage["count"] > len(damage["lines"]) else ""
    return f"(lines {shown}{more})"


def _bot_lines(summary: dict[str, Any]) -> list[str]:
    bots = summary["bots"]
    if bots is None:
        return ["bots: unknown (no session.started)"]
    lines = [f"bots ({'debug' if summary['debug'] else 'not debug'}):"]
    for bot in bots:
        names = ", ".join(map(str, bot["decision_makers"])) or "none"
        lines.append(f"  {bot['ign']}  {bot['bot_class']}  [{names}]")
    return lines


def _ended_line(ended: dict[str, Any] | None) -> str:
    if ended is None:
        return "ended: still running (no session.ended)"
    line = f"ended: {ended['cause']} at {format_time(ended['t'])}"
    return f"{line}: {ended['error']}" if ended["error"] else line


def _report_damage(session: Session) -> None:
    """Malformed lines and degraded payloads, on stderr so `--json` stays clean."""
    summary = summarize(session)
    for line in _damage_lines(summary):
        _err(line)


def _resolve(session: Session, time: TimeArg | None) -> float | None:
    return None if time is None else session.resolve(time)


def _out(text: str) -> None:
    sys.stdout.write(text + "\n")


def _err(text: str) -> None:
    sys.stderr.write(text + "\n")


# --- Arguments --------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "dir",
        nargs="?",
        type=Path,
        metavar="DIR",
        help="the Session directory (default: the newest under logs/)",
    )
    common.add_argument("--json", action="store_true", help="one JSON object per line")

    parser = argparse.ArgumentParser(
        prog="python -m botting.session",
        description="Read one Session's Telemetry Records.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "summary", parents=[common], help="what ran, what happened, how it ended"
    )

    events = commands.add_parser(
        "events", parents=[common], help="the matching records, one per line"
    )
    events.add_argument(
        "--type", default="*", metavar="GLOB", help="Event Type glob (default: *)"
    )
    events.add_argument(
        "--where",
        action="append",
        default=[],
        type=_argument(parse_where),
        metavar="KEY=GLOB",
        help="a payload field matches GLOB; repeat to require several",
    )
    for bound in ("since", "until"):
        events.add_argument(
            f"--{bound}",
            type=_argument(parse_time),
            metavar="T",
            help=f"records {'at or after' if bound == 'since' else 'at or before'} T",
        )
    events.add_argument(
        "--limit", type=_positive, metavar="N", help="at most N records"
    )

    around = commands.add_parser(
        "around", parents=[common], help="every record within S seconds of T"
    )
    around.add_argument("--at", required=True, type=_argument(parse_time), metavar="T")
    around.add_argument(
        "--window",
        type=_seconds,
        default=DEFAULT_WINDOW,
        metavar="S",
        help=f"seconds either side of T (default: {DEFAULT_WINDOW:g})",
    )

    frame = commands.add_parser(
        "frame", parents=[common], help="a PNG of the Session's video at T"
    )
    frame.add_argument("--at", required=True, type=_argument(parse_time), metavar="T")
    frame.add_argument(
        "--box",
        type=_argument(parse_box),
        metavar="l,t,r,b",
        help="crop to this region, in screen pixels",
    )
    frame.add_argument(
        "--scale",
        type=_factor,
        default=1.0,
        metavar="F",
        help="resize the (cropped) frame by F (default: 1)",
    )
    return parser


def _argument[T](parse: Callable[[str], T]) -> Callable[[str], T]:
    """Turn a parser's `ValueError` into argparse's own error and exit code."""

    def convert(text: str) -> T:
        try:
            return parse(text)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from None

    return convert


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text} is not a positive count")
    return value


def _factor(text: str) -> float:
    value = float(text)
    if not 0 < value <= 8:
        raise argparse.ArgumentTypeError(f"{text} is not a scale in (0, 8]")
    return value


def _seconds(text: str) -> float:
    value = float(text)
    if value < 0:
        raise argparse.ArgumentTypeError(f"{text} is not a number of seconds")
    return value
