"""
`python -m botting.session summary`, `events` and `around`, through `main`,
on a `telemetry.jsonl` written into `tmp_path`.

The fixture Session runs two Bots for 30 s. One record, from the Peripherals
process, comes 0.4 s *before* `session.started`, as one really can
(`SessionManager.__enter__` starts that process before `launch` emits the
start), so every command is checked against a negative time too.
"""

import datetime
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from botting.session import cli, reading
from botting.session.cli import main
from botting.session.reading import format_time, parse_time

ZONE = datetime.timezone(datetime.timedelta(hours=-5))
#: Wall-clock time of `session.started` in the fixture.
START = datetime.datetime(2026, 11, 8, 10, 0, 0, tzinfo=ZONE)

#: One record: seconds from START, Event Type, payload, Correlation ID.
Spec = tuple[float, str, dict[str, Any], str | None]

BOTS = [
    {"ign": "Alpha", "bot_class": "FarmBot", "decision_makers": ["Rotation", "Rebuff"]},
    {"ign": "Beta", "bot_class": "Leech", "decision_makers": []},
]

SESSION: list[Spec] = [
    (-0.4, "recording.started", {"path": "rec.avi", "fps": 10}, None),
    (0.0, "session.started", {"bots": BOTS, "debug": False}, None),
    (
        1.0,
        "action.scheduled",
        {"identifier": "Rotation(Alpha)", "priority": 1},
        "aaaaaaaa-1",
    ),
    (
        2.0,
        "action.finished",
        {"identifier": "Rotation(Alpha)", "outcome": "completed", "elapsed_ms": 1000},
        "aaaaaaaa-1",
    ),
    (
        3.5,
        "action.scheduled",
        {"identifier": "Rebuff(Alpha)", "priority": 3},
        "bbbbbbbb-2",
    ),
    (
        4.0,
        "action.blocked",
        {"identifier": "Rotation(Alpha)", "priority": 1},
        "cccccccc-3",
    ),
    (
        5.0,
        "action.finished",
        {"identifier": "Rebuff(Alpha)", "outcome": "raised", "elapsed_ms": 1500},
        "bbbbbbbb-2",
    ),
    (
        9.0,
        "action.finished",
        {"identifier": "Rotation(Alpha)", "outcome": "cancelled", "elapsed_ms": 50},
        "dddddddd-4",
    ),
    (12.0, "combat.mobs_hit", {"mob_count": 3, "direction": "left"}, "eeeeeeee-5"),
    (20.0, "combat.mobs_hit", {"mob_count": 0, "direction": None}, "ffffffff-6"),
    (
        25.0,
        "decision.disabled",
        {"target": "Rotation", "detail": {"by": "Rebuff"}},
        None,
    ),
    (30.0, "session.ended", {"cause": "completed", "error": None}, None),
]


def envelope(spec: Spec, logger: str = "botting.test") -> dict[str, Any]:
    seconds, event_type, payload, cid = spec
    return {
        "timestamp": (START + datetime.timedelta(seconds=seconds)).isoformat(),
        "correlation_id": cid,
        "logger_name": logger,
        "event_type": event_type,
        "payload": payload,
    }


def write_session(directory: Path, lines: Sequence[Spec | str]) -> Path:
    """A Session directory whose telemetry holds `lines`; a str goes in as is."""
    directory.mkdir(parents=True, exist_ok=True)
    text = "".join(
        f"{line if isinstance(line, str) else json.dumps(envelope(line))}\n"
        for line in lines
    )
    (directory / "telemetry.jsonl").write_text(text, encoding="utf-8")
    return directory


@pytest.fixture
def session(tmp_path: Path) -> Path:
    return write_session(tmp_path / "logs" / "2026-11-08_10-00-00", SESSION)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str], str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out.splitlines(), captured.err


def json_lines(out: list[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out]


# --- summary ----------------------------------------------------------------------


def test_summary_says_what_ran_what_happened_and_how_it_ended(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(capsys, "summary", str(session))

    assert code == 0, err
    assert out == [
        f"session: {session}",
        "origin: 2026-11-08T10:00:00-05:00 (session.started)",
        "duration: 00:30.0",
        "records: 12 (1 before session.started, the first at -00:00.4)",
        "bots (not debug):",
        "  Alpha  FarmBot  [Rotation, Rebuff]",
        "  Beta  Leech  [none]",
        "event types:",
        "  action.finished    3",
        "  action.scheduled   2",
        "  combat.mobs_hit    2",
        "  action.blocked     1",
        "  decision.disabled  1",
        "  recording.started  1",
        "  session.ended      1",
        "  session.started    1",
        "action.finished:",
        "  Rebuff(Alpha)    raised 1",
        "  Rotation(Alpha)  cancelled 1  completed 1",
        "ended: completed at +00:30.0",
    ]


def test_summary_json_is_one_object(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "summary", str(session), "--json")

    assert code == 0
    [summary] = json_lines(out)
    assert summary["origin_from"] == "session.started"
    assert summary["duration_s"] == 30.0
    assert summary["records"] == 12
    assert summary["before_origin"] == 1
    assert summary["first_t"] == -0.4
    assert summary["bots"] == BOTS
    assert summary["debug"] is False
    assert summary["event_types"]["action.finished"] == 3
    assert summary["actions"] == {
        "Rebuff(Alpha)": {"raised": 1},
        "Rotation(Alpha)": {"cancelled": 1, "completed": 1},
    }
    assert summary["ended"] == {"t": 30.0, "cause": "completed", "error": None}
    assert summary["malformed"] == {"count": 0, "lines": []}


def test_a_running_session_is_still_running_and_its_duration_is_so_far(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = write_session(tmp_path / "s", SESSION[:-1])

    code, out, _ = run(capsys, "summary", str(directory))

    assert code == 0
    assert "duration: 00:25.0 so far" in out
    assert out[-1] == "ended: still running (no session.ended)"


def test_an_error_ending_names_the_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ended: Spec = (
        7.0,
        "session.ended",
        {"cause": "error", "error": "ValueError: boom"},
        None,
    )
    directory = write_session(tmp_path / "s", [*SESSION[:3], ended])

    _, out, _ = run(capsys, "summary", str(directory))

    assert out[-1] == "ended: error at +00:07.0: ValueError: boom"


def test_without_session_started_the_clock_starts_at_the_first_record(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # In file order, the later record comes first: the clock is the earliest.
    directory = write_session(tmp_path / "s", [SESSION[3], SESSION[2]])

    _, out, _ = run(capsys, "summary", str(directory))
    _, events, _ = run(capsys, "events", str(directory))

    assert "origin: 2026-11-08T10:00:01-05:00 (first record)" in out
    assert "records: 2" in out
    assert "bots: unknown (no session.started)" in out
    assert [line.split()[0:2] for line in events] == [
        ["+00:00.0", "action.scheduled"],
        ["+00:01.0", "action.finished"],
    ]


def test_an_empty_telemetry_file_summarises_as_no_records(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = write_session(tmp_path / "s", [])

    code, out, _ = run(capsys, "summary", str(directory))
    events_code, events, _ = run(capsys, "events", str(directory), "--since", "+00:01")

    assert code == 0
    assert out[1] == "records: 0"
    assert (events_code, events) == (0, [])


# --- damage -----------------------------------------------------------------------


DEGRADED: Spec = (
    6.0,
    "combat.mobs_hit",
    {"telemetry_encode_error": "TypeError('keys')", "payload_repr": "{(1, 2): 3}"},
    "gggggggg-7",
)


@pytest.fixture
def damaged(tmp_path: Path) -> Path:
    return write_session(
        tmp_path / "s",
        [
            SESSION[1],
            "not json at all",
            '["a", "list"]',
            json.dumps({**envelope(SESSION[2]), "timestamp": "yesterday"}),
            json.dumps(
                {k: v for k, v in envelope(SESSION[2]).items() if k != "payload"}
            ),
            "",
            DEGRADED,
            SESSION[-1],
            '{"timestamp": "2026-11-08T10:00:3',  # a line still being written
        ],
    )


def test_malformed_lines_and_degraded_payloads_are_counted_in_the_summary(
    damaged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "summary", str(damaged))

    assert code == 0
    assert "records: 3" in out
    assert "malformed lines: 5 (lines 2, 3, 4, 5, 9)" in out
    assert "degraded payloads: 1 (lines 7)" in out


def test_events_keep_degraded_records_and_report_damage_on_stderr(
    damaged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = run(capsys, "events", str(damaged), "--type", "combat.*", "--json")

    assert code == 0
    [record] = json_lines(out)
    assert record["line"] == 7
    assert record["payload"]["telemetry_encode_error"] == "TypeError('keys')"
    assert err.splitlines() == [
        "malformed lines: 5 (lines 2, 3, 4, 5, 9)",
        "degraded payloads: 1 (lines 7)",
    ]


def test_a_long_damage_list_is_cut_and_still_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = write_session(tmp_path / "s", [SESSION[1], *["{"] * 12])

    _, out, _ = run(capsys, "summary", str(directory))

    assert "malformed lines: 12 (lines 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, ...)" in out


# --- which Session ----------------------------------------------------------------


def test_without_dir_the_newest_session_with_telemetry_is_read_running_or_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    logs = tmp_path / "logs"
    write_session(logs / "2026-11-08_09-00-00", SESSION)
    newest = write_session(logs / "2026-11-08_10-00-00", SESSION[:4])
    (logs / "2026-11-08_11-00-00").mkdir()  # no telemetry yet
    monkeypatch.setattr(reading, "LOGS_ROOT", logs)

    code, out, _ = run(capsys, "summary")

    assert code == 0
    assert out[0] == f"session: {newest}"
    assert out[-1] == "ended: still running (no session.ended)"


def test_no_session_to_read_is_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(reading, "LOGS_ROOT", tmp_path / "absent")
    (tmp_path / "empty").mkdir()

    no_logs = run(capsys, "summary")
    no_file = run(capsys, "events", str(tmp_path / "empty"))

    assert no_logs[0] == 1
    assert "error: no directory under" in no_logs[2]
    assert no_file[0] == 1
    assert "has no telemetry.jsonl" in no_file[2]


def test_dir_may_name_the_telemetry_file_itself(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "summary", str(session / "telemetry.jsonl"), "--json")

    assert code == 0
    assert json_lines(out)[0]["records"] == 12


# --- events -----------------------------------------------------------------------


def test_events_prints_one_line_per_record_in_time_order(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, err = run(capsys, "events", str(session))

    assert err == ""
    assert len(out) == 12
    assert out[0] == ('-00:00.4  recording.started  {"path":"rec.avi","fps":10}')
    assert out[2] == (
        "+00:01.0  action.scheduled  cid=aaaaaaaa  "
        '{"identifier":"Rotation(Alpha)","priority":1}'
    )


def test_events_type_is_a_glob(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(capsys, "events", str(session), "--type", "action.*", "--json")

    assert [r["event_type"] for r in json_lines(out)] == [
        "action.scheduled",
        "action.finished",
        "action.scheduled",
        "action.blocked",
        "action.finished",
        "action.finished",
    ]


@pytest.mark.parametrize(
    ("where", "expected_lines"),
    [
        # A string field is matched as it is.
        (["outcome=c*"], [4, 8]),
        # Several conditions must all hold.
        (["outcome=c*", "identifier=Rotation(Alpha)"], [4, 8]),
        (["outcome=completed", "elapsed_ms=50"], []),
        # Any other value is matched as its JSON.
        (["elapsed_ms=1?00"], [4, 7]),
        (["direction=null"], [10]),
        # A dotted key reaches into a nested object.
        (["detail.by=Re*"], [11]),
        # A missing field never matches, even `*`.
        (["no_such_field=*"], []),
        # The glob is everything after the first `=`.
        (["identifier=*=*"], []),
    ],
)
def test_events_where_matches_payload_fields(
    session: Path,
    capsys: pytest.CaptureFixture[str],
    where: list[str],
    expected_lines: list[int],
) -> None:
    argv = ["events", str(session), "--json"]
    for condition in where:
        argv += ["--where", condition]

    _, out, _ = run(capsys, *argv)

    assert [r["line"] for r in json_lines(out)] == expected_lines


@pytest.mark.parametrize(
    ("since", "until", "expected_lines"),
    [
        # +mm:ss[.s]
        ("+00:03.5", "+00:05", [5, 6, 7]),
        # Plain seconds.
        ("3.5", "5", [5, 6, 7]),
        # ISO-8601, with and without fractional seconds.
        ("2026-11-08T10:00:03.500-05:00", "2026-11-08T10:00:05-05:00", [5, 6, 7]),
        # The same instant written in another zone.
        ("2026-11-08T15:00:03.500+00:00", "2026-11-08T15:00:05+00:00", [5, 6, 7]),
        # Before session.started: the minus sign reaches it.
        ("-00:01", "-0.1", [1]),
        ("-1", "+00:00", [1, 2]),
    ],
)
def test_events_since_and_until_take_every_time_format_inclusively(
    session: Path,
    capsys: pytest.CaptureFixture[str],
    since: str,
    until: str,
    expected_lines: list[int],
) -> None:
    _, out, _ = run(
        capsys, "events", str(session), "--since", since, "--until", until, "--json"
    )

    assert [r["line"] for r in json_lines(out)] == expected_lines


def test_events_since_alone_and_until_alone(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, since, _ = run(capsys, "events", str(session), "--since", "+00:20", "--json")
    _, until, _ = run(capsys, "events", str(session), "--until", "0", "--json")

    assert [r["line"] for r in json_lines(since)] == [10, 11, 12]
    assert [r["line"] for r in json_lines(until)] == [1, 2]


def test_events_limit_keeps_the_first_n_and_says_how_many_matched(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, err = run(
        capsys, "events", str(session), "--type", "action.*", "--limit", "2"
    )

    assert len(out) == 2
    assert out[0].startswith("+00:01.0  action.scheduled")
    assert err == "limit reached: 2 of 6 matching records shown\n"


def test_events_json_is_the_envelope_with_its_time_and_line(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        capsys, "events", str(session), "--type", "action.blocked", "--json"
    )

    assert json_lines(out) == [
        {
            "t": 4.0,
            "line": 6,
            **envelope(SESSION[5]),
        }
    ]


@pytest.mark.parametrize(
    "argv",
    [
        ["--since", "21:14"],  # mm:ss without a sign could be a clock time
        ["--since", "+00:75"],
        ["--until", "soon"],
        ["--where", "no-equals-sign"],
        ["--where", "=glob"],
        ["--limit", "0"],
    ],
)
def test_events_refuses_bad_arguments_with_exit_code_2(
    session: Path, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["events", str(session), *argv])

    assert exit_info.value.code == 2
    assert capsys.readouterr().out == ""


# --- around -----------------------------------------------------------------------


def test_around_shows_the_window_either_side_of_t_with_a_marker(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(
        capsys, "around", str(session), "--at", "+00:04", "--window", "1"
    )

    assert code == 0
    assert [line[:28] for line in out] == [
        "+00:03.5  action.scheduled  ",
        "---------- +00:04.0 --------",
        "+00:04.0  action.blocked  ci",
        "+00:05.0  action.finished  c",
    ]


def test_around_defaults_to_five_seconds(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(capsys, "around", str(session), "--at", "15", "--json")

    assert cli.DEFAULT_WINDOW == 5.0
    assert [r["line"] for r in json_lines(out)] == [9, 10]


def test_around_reaches_before_session_started(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        capsys, "around", str(session), "--at", "-00:00.4", "--window", "0.5"
    )

    assert out == [
        "---------- -00:00.4 ----------",
        '-00:00.4  recording.started  {"path":"rec.avi","fps":10}',
        f"+00:00.0  session.started  {json.dumps({'bots': BOTS, 'debug': False}, separators=(',', ':'))}",
    ]


def test_around_takes_an_iso_timestamp(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = run(
        capsys,
        "around",
        str(session),
        "--at",
        "2026-11-08T10:00:30-05:00",
        "--window",
        "0",
    )

    assert out == [
        "---------- +00:30.0 ----------",
        '+00:30.0  session.ended  {"cause":"completed","error":null}',
    ]


def test_around_requires_at(session: Path) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["around", str(session)])

    assert exit_info.value.code == 2


# --- the clock --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.0, "+00:00.0"),
        (97.5, "+01:37.5"),
        (-0.4, "-00:00.4"),
        (-0.04, "+00:00.0"),
        (59.96, "+01:00.0"),
        (4530.0, "+75:30.0"),
    ],
)
def test_format_time(seconds: float, text: str) -> None:
    assert format_time(seconds) == text


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("+01:37.5", 97.5),
        ("+1:7", 67.0),
        ("-00:00.4", -0.4),
        ("97.5", 97.5),
        ("-2", -2.0),
        ("+3", 3.0),
    ],
)
def test_parse_time_relative(text: str, seconds: float) -> None:
    parsed = parse_time(text)

    assert parsed.at is None
    assert parsed.seconds == pytest.approx(seconds)


def test_parse_time_reads_a_naive_timestamp_as_local_time() -> None:
    parsed = parse_time("2026-11-08T10:00:30")

    assert parsed.at == datetime.datetime(2026, 11, 8, 10, 0, 30).astimezone()
