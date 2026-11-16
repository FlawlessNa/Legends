"""
`python -m botting.session watch` and `stop`, through `main`, on a
`telemetry.jsonl` in `tmp_path` that a thread appends to while the command
runs, as a live Session's Main Process would.
"""

import datetime
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from botting.session import live
from botting.session.cli import main
from botting.stop_file import STOP_FILENAME

START = datetime.datetime(2026, 11, 8, 10, 0, 0, tzinfo=datetime.UTC)


def line(seconds: float, event_type: str, payload: dict[str, Any] | None = None) -> str:
    return json.dumps(
        {
            "timestamp": (START + datetime.timedelta(seconds=seconds)).isoformat(),
            "correlation_id": None,
            "logger_name": "botting.test",
            "event_type": event_type,
            "payload": payload or {},
        }
    )


STARTED = line(0, "session.started", {"bots": [], "debug": False})

#: Starts a writer thread while the command runs (the `in_background` fixture).
Background = Callable[[Callable[[], None]], None]
REACHED = "movement.target_reached"


def ended(seconds: float, cause: str = "stop_file") -> str:
    return line(seconds, "session.ended", {"cause": cause, "error": None})


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live, "FOLLOW_INTERVAL", 0.01)


@pytest.fixture
def session(tmp_path: Path) -> Path:
    (tmp_path / "telemetry.jsonl").write_text(STARTED + "\n", encoding="utf-8")
    return tmp_path


def append(session: Path, *lines: str) -> None:
    with (session / "telemetry.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("".join(f"{text}\n" for text in lines))


@pytest.fixture
def in_background() -> Iterator[Background]:
    """Runs a writer on a thread while the command runs; joined afterwards."""
    threads: list[threading.Thread] = []

    def start(writer: Callable[[], None]) -> None:
        thread = threading.Thread(target=writer, daemon=True)
        threads.append(thread)
        thread.start()

    yield start
    for thread in threads:
        thread.join(timeout=5)


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out.strip(), captured.err


# --- watch ------------------------------------------------------------------------


def test_watch_exits_0_once_the_count_is_met(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    def writer() -> None:
        for i in range(1, 4):
            time.sleep(0.05)
            append(session, line(i, REACHED), line(i + 0.5, "action.finished"))

    in_background(writer)
    code, out, _ = run(
        capsys,
        "watch",
        str(session),
        "--until-type",
        "movement.*",
        "--count",
        "3",
        "--timeout",
        "5",
    )

    assert code == 0
    assert out == "met: 3 of 3 movement.*, the last at +00:03.0"


def test_watch_exits_1_on_timeout(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    in_background(lambda: append(session, line(1, REACHED)))
    code, out, _ = run(
        capsys,
        "watch",
        str(session),
        "--until-type",
        REACHED,
        "--count",
        "2",
        "--timeout",
        "0.3",
    )

    assert code == 1
    assert out == f"timeout: 1 of 2 {REACHED} after 0.3 s"


def test_watch_exits_2_when_the_session_ends_first(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    def writer() -> None:
        time.sleep(0.05)
        append(session, line(1, REACHED))
        time.sleep(0.05)
        append(session, ended(2, cause="completed"))

    in_background(writer)
    code, out, _ = run(
        capsys,
        "watch",
        str(session),
        "--until-type",
        REACHED,
        "--count",
        "2",
        "--timeout",
        "5",
    )

    assert code == 2
    assert out == f"ended first: completed at +00:02.0, with 1 of 2 {REACHED}"


def test_watch_counts_from_the_start_of_the_file(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Records already written count: the answer doesn't depend on when it started."""
    append(session, line(1, REACHED), line(2, REACHED))

    code, _, _ = run(
        capsys, "watch", str(session), "--until-type", REACHED, "--count", "2"
    )

    assert code == 0


def test_watch_on_a_finished_session_short_of_the_count_exits_2(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append(session, line(1, REACHED), ended(3))

    code, _, _ = run(
        capsys, "watch", str(session), "--until-type", REACHED, "--count", "2"
    )

    assert code == 2


def test_watch_met_by_the_last_records_before_session_ended_exits_0(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append(session, line(1, REACHED), ended(3))

    code, _, _ = run(capsys, "watch", str(session), "--until-type", REACHED)

    assert code == 0


def test_watch_counts_session_ended_itself_when_it_matches(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--until-type session.ended` is a way to wait for the end, and that is met."""
    append(session, ended(3))

    code, _, _ = run(capsys, "watch", str(session), "--until-type", "session.ended")

    assert code == 0


def test_watch_json_says_how_it_ended(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append(session, line(1.5, REACHED))

    code, out, _ = run(capsys, "watch", str(session), "--until-type", REACHED, "--json")

    result = json.loads(out)
    assert code == 0
    assert (result["result"], result["matched"], result["count"]) == ("met", 1, 1)
    assert result["record"]["t"] == 1.5
    assert result["record"]["event_type"] == REACHED


def test_watch_waits_for_a_line_still_being_written(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    """Half a line is no record yet: it is read once its newline arrives."""
    record = line(1, REACHED)

    def writer() -> None:
        path = session / "telemetry.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(record[:20])
            handle.flush()
            time.sleep(0.1)
            handle.write(record[20:] + "\n")

    in_background(writer)
    code, _, err = run(
        capsys, "watch", str(session), "--until-type", REACHED, "--timeout", "5"
    )

    assert code == 0
    assert err == ""


def test_watch_skips_and_reports_malformed_lines(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append(session, "{not json", line(1, REACHED))

    code, _, err = run(capsys, "watch", str(session), "--until-type", REACHED)

    assert code == 0
    assert "malformed lines: 1" in err


def test_watch_without_a_session_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run(capsys, "watch", str(tmp_path), "--until-type", REACHED)

    assert code == 1
    assert "has no telemetry.jsonl" in err


# --- stop -------------------------------------------------------------------------


def _end_once_stop_appears(session: Path) -> Callable[[], None]:
    """
    What a Session does with the stop file: notice it, then end. Like the
    Session's own `watch_stop_file`, a file that can't be read yet is looked at
    again: on Windows, opening it while `request_stop`'s rename is finishing is
    refused (`PermissionError`).
    """

    def writer() -> None:
        deadline = time.monotonic() + 5
        while True:
            try:
                reason = (session / STOP_FILENAME).read_text(encoding="utf-8")
                break
            except OSError:
                if time.monotonic() > deadline:
                    return
                time.sleep(0.01)
        append(session, line(5, "session.stop_requested", {"reason": reason}), ended(6))

    return writer


def test_stop_writes_the_reason_and_exits_0_on_session_ended(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    in_background(_end_once_stop_appears(session))

    code, out, _ = run(capsys, "stop", str(session), "--reason", "tests done")

    assert code == 0
    assert out == "stopped: stop_file at +00:06.0"
    assert (session / STOP_FILENAME).read_text(encoding="utf-8") == "tests done"


def test_stop_ends_when_the_stop_file_is_unreadable_at_first(
    session: Path,
    capsys: pytest.CaptureFixture[str],
    in_background: Background,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    On Windows, opening the stop file while `request_stop`'s rename is still
    finishing is refused with `PermissionError`, and under load the stand-in
    Session met that (#472). The Session waits it out (`watch_stop_file`), and
    so must its stand-in here, or `stop` never sees `session.ended`.
    """
    real = Path.read_text
    refused: list[Path] = []

    def in_use_once(self: Path, encoding: str | None = None) -> str:
        if self.name == STOP_FILENAME and not refused:
            refused.append(self)
            raise PermissionError(13, "Permission denied", str(self))
        return real(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", in_use_once)
    in_background(_end_once_stop_appears(session))

    code, out, _ = run(capsys, "stop", str(session), "--timeout", "3")

    assert refused
    assert code == 0
    assert out == "stopped: stop_file at +00:06.0"


def test_stop_without_a_reason_writes_the_default(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    in_background(_end_once_stop_appears(session))

    code, _, _ = run(capsys, "stop", str(session))

    assert code == 0
    assert (session / STOP_FILENAME).read_text(encoding="utf-8") == live.DEFAULT_REASON


def test_stop_exits_1_on_timeout(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run(capsys, "stop", str(session), "--timeout", "0.2")

    assert code == 1
    assert out.startswith("timeout: no session.ended after 0.2 s")
    assert (session / STOP_FILENAME).exists()


def test_stop_on_a_session_that_already_ended_writes_nothing(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    append(session, ended(9, cause="completed"))

    code, out, _ = run(capsys, "stop", str(session))

    assert code == 0
    assert out == "already ended: completed at +00:09.0"
    assert not (session / STOP_FILENAME).exists()


def test_stop_json_says_how_it_ended(
    session: Path, capsys: pytest.CaptureFixture[str], in_background: Background
) -> None:
    in_background(_end_once_stop_appears(session))

    code, out, _ = run(capsys, "stop", str(session), "--json")

    result = json.loads(out)
    assert code == 0
    assert result["result"] == "stopped"
    assert result["record"]["payload"] == {"cause": "stop_file", "error": None}


def test_stop_without_a_session_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = run(capsys, "stop", str(tmp_path / "missing"))

    assert code == 1
    assert not (tmp_path / "missing").exists()
