"""
`toolkit.trial_report` (#536): per-move verdicts, clusters and loop timing, on a
small synthetic Trial record and Session built here. Nothing reads a client.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from maple.calibration.records import (
    CycleRecord,
    JsonlRecordWriter,
    MovementSummary,
    PositionRecord,
    SampleRecord,
    ScheduleHeader,
    TrialOutcome,
)
from maple.calibration.specs import Knobs
from toolkit import trial_report

#: Record clock (`time.monotonic()`) of a Trial's t = 0.
T0 = 1000.0
#: The Session's local wall clock at record-clock T0.
ZONE = timezone(timedelta(hours=-5))
WALL0 = datetime(2026, 11, 15, 8, 0, 0, tzinfo=ZONE)

Point = tuple[float, float]


def move(
    kind: str, start: Point, end: Point, length: float | None = None
) -> MovementSummary:
    if length is None:
        length = abs(end[0] - start[0]) or abs(end[1] - start[1])
    return MovementSummary(kind, length, False, False, start=start, end=end)


class Trial:
    """One Trial's lines, written in time order."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.lines: list[CycleRecord | SampleRecord] = []
        self.cycle = 0
        self.cid = ""

    def cycle_at(
        self, t: float, at: Point | None, plan: Sequence[MovementSummary] = ()
    ) -> str:
        self.cycle += 1
        self.cid = f"{self.name}-{self.cycle}"
        position = PositionRecord(
            "read" if at else "unsure", at, "fused" if at else None, T0 + t
        )
        self.lines.append(
            CycleRecord(
                "s",
                "b",
                self.name,
                "measuring",
                self.cycle,
                t,
                "2026-11-15T13:00:00+00:00",
                position,
                (0, 0),
                0.0 if at else None,
                bool(plan),
                self.cid,
                tuple(plan),
            )
        )
        return self.cid

    def reads(self, *reads: tuple[float, float, float]) -> None:
        for t, x, y in reads:
            self.lines.append(
                SampleRecord(
                    "s",
                    "b",
                    self.name,
                    "measuring",
                    t,
                    PositionRecord("read", (x, y), "fused", T0 + t),
                    self.cid,
                )
            )

    def outcome(self, duration: float) -> TrialOutcome:
        return TrialOutcome(
            "s",
            "b",
            self.name,
            Knobs(),
            (0, 0),
            (60, -50),
            16.0,
            60.0,
            "arrived",
            1.0,
            duration,
            duration,
            self.cycle,
            0,
            0,
            0,
            "2026-11-15T13:00:00+00:00",
        )


def write(path: Path, *trials: tuple[Trial, float]) -> Path:
    with JsonlRecordWriter(path) as sink:
        sink.write(
            ScheduleHeader("s", "Some Map", "2026-11-15T13:00:00+00:00", "SECRETBOX")
        )
        for trial, duration in trials:
            for line in trial.lines:
                sink.write(line)
            sink.write(trial.outcome(duration))
    return path


def judged(path: Path, trial: str) -> dict[int, trial_report.Judged]:
    run = trial_report.analyze(path, None)
    return {j.cycle: j for j in run.judged[trial]}


# --- the scenarios ----------------------------------------------------------------


def overshoot() -> Trial:
    """A walk to the take-off, a jump that lands 40 px past, a walk back."""
    trial = Trial("overshoot")
    trial.cycle_at(
        0.0,
        (-50, 0),
        [
            move("WALK_RIGHT", (-50, 0), (0, 0)),
            move("JUMP_RIGHT", (0, 0), (60, -50), 60),
        ],
    )
    trial.reads(
        (0.12, -35, 0),
        (0.24, -20, 0),
        (0.36, -5, 0),
        (0.48, 10, -40),
        (0.60, 40, -60),
        (0.72, 80, -55),
        (0.84, 100, -50),
        (0.96, 100, -50),
        (1.08, 100, -50),
    )
    trial.cycle_at(1.2, (100, -50), [move("WALK_LEFT", (100, -50), (60, -50))])
    trial.reads((1.32, 80, -50), (1.44, 62, -50))
    trial.cycle_at(1.56, (62, -50))
    return trial


@pytest.fixture
def record(tmp_path: Path) -> Path:
    return write(tmp_path / "run.jsonl", (overshoot(), 1.56))


def test_a_jump_landing_past_the_plan_is_long_with_its_error_vector(
    record: Path,
) -> None:
    cycle = judged(record, "overshoot")[1]

    assert cycle.kind == "jump"
    assert cycle.lead == 50
    assert cycle.takeoff == "on time"
    assert cycle.landing == (100, -50)
    assert cycle.error == (40, 0)
    assert cycle.verdict == "long"


def test_a_walk_in_reach_is_judged_on_where_it_stopped(record: Path) -> None:
    cycle = judged(record, "overshoot")[2]

    assert cycle.kind == "walk"
    assert cycle.along == pytest.approx(-2)
    assert cycle.verdict == "ok"


def test_a_take_off_before_the_planned_x_is_early(tmp_path: Path) -> None:
    trial = Trial("early")
    trial.cycle_at(
        0.0,
        (-30, 0),
        [
            move("WALK_RIGHT", (-30, 0), (0, 0)),
            move("JUMP_RIGHT", (0, 0), (60, -50), 60),
        ],
    )
    trial.reads(
        (0.12, -20, 0),
        (0.24, -15, -30),
        (0.36, 5, -55),
        (0.48, 25, -50),
        (0.60, 25, -50),
        (0.72, 25, -50),
    )
    trial.cycle_at(0.84, (25, -50))
    cycle = judged(write(tmp_path / "r.jsonl", (trial, 0.84)), "early")[1]

    assert cycle.takeoff == "early"
    assert cycle.verdict == "short, early take-off"


def test_a_landing_far_below_take_off_and_plan_is_a_fall(tmp_path: Path) -> None:
    trial = Trial("fall")
    trial.cycle_at(0.0, (0, 0), [move("JUMP_RIGHT", (0, 0), (60, -50), 60)])
    trial.reads(
        (0.12, 15, -40),
        (0.24, 35, -45),
        (0.36, 55, -20),
        (0.48, 70, 40),
        (0.60, 80, 100),
        (0.72, 80, 100),
        (0.84, 80, 100),
    )
    trial.cycle_at(0.96, (80, 100))
    cycle = judged(write(tmp_path / "r.jsonl", (trial, 0.96)), "fall")[1]

    assert cycle.verdict == "fell"


def test_going_down_the_rope_at_a_climbs_pace_is_no_take_off(tmp_path: Path) -> None:
    trial = Trial("climb")
    trial.cycle_at(0.0, (0, 0), [move("JUMP_LEFT", (0, 0), (-60, 100), 60)])
    trial.reads(
        (0.12, 0, 12), (0.24, 0, 24), (0.36, 0, 36), (0.48, 0, 48), (0.60, 0, 60)
    )
    trial.cycle_at(0.72, (0, 72))
    cycle = judged(write(tmp_path / "r.jsonl", (trial, 0.72)), "climb")[1]

    assert cycle.takeoff == "climbed"
    assert cycle.verdict == "no take-off"


def retries() -> Trial:
    """The same jump tried three times, landing 40 px past it every time."""
    trial = Trial("retries")
    jump = move("JUMP_RIGHT", (0, 0), (60, -50), 60)
    flight = (
        (0.12, 15, -40),
        (0.24, 40, -50),
        (0.36, 70, -30),
        (0.48, 100, 0),
        (0.60, 100, 0),
        (0.72, 100, 0),
    )
    trial.cycle_at(0.0, (0, 0), [jump])
    trial.reads(*flight)
    for start in (0.84, 2.16):
        trial.cycle_at(start, (100, 0), [move("WALK_LEFT", (100, 0), (0, 0)), jump])
        trial.reads(
            *(
                (start + dt, x, 0.0)
                for dt, x in ((0.12, 75), (0.24, 50), (0.36, 25), (0.48, 0))
            ),
            *((start + 0.48 + dt, x, y) for dt, x, y in flight),
        )
    trial.cycle_at(3.48, (100, 0))
    return trial


def test_consecutive_tries_of_one_move_are_a_cluster_with_a_hypothesis(
    tmp_path: Path,
) -> None:
    run = trial_report.analyze(write(tmp_path / "r.jsonl", (retries(), 3.48)), None)

    (cluster,) = run.clusters
    assert [j.cycle for j in cluster.tries] == [1, 2, 3]
    assert [j.verdict for j in cluster.tries] == ["long", "long", "long"]
    assert cluster.lost == pytest.approx(2.16)
    assert "past the landing every time" in trial_report.hypothesis(cluster)


# --- the Session ------------------------------------------------------------------


def wall(t: float) -> datetime:
    return WALL0 + timedelta(seconds=t)


def session_for(record: Path, directory: Path) -> Path:
    """A Session for `overshoot`: its reads, two Actions and two Path lines,
    with a player name in every place a Session carries one."""
    directory.mkdir()
    events: list[dict[str, object]] = []
    for line in record.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["kind"] in ("cycle", "sample") and row["position"]:
            x, y = row["position"]
            events.append(
                {
                    "timestamp": wall(row["frame_time"] - T0).isoformat(),
                    "correlation_id": None,
                    "event_type": "position.read",
                    "payload": {
                        "status": "read",
                        "x": x,
                        "y": y,
                        "detail": "SecretName",
                    },
                }
            )
    for cid, scheduled, finished, ms in (
        ("overshoot-1", 0.05, 1.05, 1000),
        ("overshoot-2", 1.25, 1.75, 500),
    ):
        for kind, t, payload in (
            ("action.scheduled", scheduled, {"identifier": "TrialRunner(SecretName)"}),
            (
                "action.finished",
                finished,
                {"identifier": "TrialRunner(SecretName)", "elapsed_ms": ms},
            ),
        ):
            events.append(
                {
                    "timestamp": wall(t).isoformat(),
                    "correlation_id": cid,
                    "event_type": kind,
                    "payload": payload,
                }
            )
    events.sort(key=lambda e: str(e["timestamp"]))
    (directory / "telemetry.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
    )

    def log(t: float, text: str) -> str:
        stamp = (
            wall(t).strftime("%Y-%m-%d %H:%M:%S,")
            + f"{wall(t).microsecond // 1000:03d}"
        )
        return (
            "DEBUG -- PROCESS Engine(SecretName) -- TASK TrialRunner(SecretName) "
            f"-- MODULE model.mechanics.movement_mechanics_v2 -- {stamp}:::{text}\n"
        )

    (directory / "session.log").write_text(
        log(0.01, "Computing path from (-50.0, 0.0) to (60.0, -50.0)")
        + log(0.02, "Movements: [...]")
        + log(1.21, "Computing path from (100.0, -50.0) to (60.0, -50.0)")
        + log(1.22, "Movements: [...]"),
        encoding="utf-8",
    )
    return directory


def test_the_session_is_put_on_the_records_clock_and_timed(
    record: Path, tmp_path: Path
) -> None:
    run = trial_report.analyze(record, session_for(record, tmp_path / "session"))
    first, second = run.judged["overshoot"][:2]

    assert run.session is not None
    assert first.dispatched_at == pytest.approx(T0 + 0.05, abs=1e-3)
    assert first.timing is not None
    assert first.timing.ended == "cut"
    timing = second.timing
    assert timing is not None
    assert timing.ended == "plan end"
    assert timing.planning == pytest.approx(0.01, abs=2e-3)
    assert timing.handoff == pytest.approx(0.03, abs=2e-3)
    assert timing.gap == pytest.approx(0.20, abs=2e-3)
    assert timing.wait == pytest.approx(0.15, abs=2e-3)
    assert timing.in_flight == pytest.approx(0.03, abs=2e-3)


def test_the_report_and_plot_are_written_without_a_name(
    record: Path, tmp_path: Path
) -> None:
    session = session_for(record, tmp_path / "session")
    out = tmp_path / "out" / "run.report.md"

    trial_report.main(
        [
            str(record),
            str(session),
            "--out",
            str(out),
            "--no-footholds",
            "--compare",
            str(record),
            "--moment",
            "overshoot@0.5",
        ]
    )

    text = out.read_text(encoding="utf-8")
    assert (tmp_path / "out" / "run.route.png").exists()
    for section in (
        "## Clusters of retries",
        "## Loop timing",
        "## Side by side",
        "## Where the time goes",
        "## Moment overshoot@0.5",
    ):
        assert section in text
    assert "SecretName" not in text
    assert "SECRETBOX" not in text


def test_the_default_cut_is_the_trial_runners() -> None:
    from maple.decision_makers.trial_runner import TrialRunner

    assert trial_report.DEFAULT_CUT == TrialRunner.DEFAULT_ACTION_DURATION


def test_the_settings_the_report_names_are_the_codes() -> None:
    """ "Where the time goes" quotes each setting's value; a change in the code
    must fail here rather than leave the report quoting the old one."""
    import re

    from botting.core.async_task_manager import AsyncTaskManager
    from maple.bots import maple_bot
    from maple.decision_makers.trial_runner import TrialRunner

    assert trial_report.LOOP_PERIOD == TrialRunner._throttle  # pyright: ignore[reportPrivateUsage]
    assert trial_report.HANDOFF_THROTTLE == AsyncTaskManager._throttle  # pyright: ignore[reportPrivateUsage]
    source = Path(maple_bot.__file__).read_text(encoding="utf-8")
    cache = re.search(r'"current_frame",.*?threshold=([\d.]+)', source, re.DOTALL)
    assert cache is not None
    assert trial_report.FRAME_CACHE == float(cache.group(1))
