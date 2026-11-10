"""
`toolkit/movement_attempts.py` (#12): Attempts counted from synthetic telemetry
streams. Nothing here reads a Session from a client; the offsets and windows are
the analyzer's Expectations, so these tests pin the *shape* of the counting
(delimitation by gesture, success per row, the verdict), not a measurement.
"""

import datetime
import json
from pathlib import Path

import pytest

from botting.session.reading import Record
from maple.calibration.records import CycleRecord, ScheduleHeader
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.telemetry_events import (
    MOVEMENT_PLAN_STARTED,
    POSITION_READ,
    plan_started_payload,
)
from toolkit.movement_attempts import analyze, main, trial_cycles

EPOCH = datetime.datetime(2026, 11, 10, tzinfo=datetime.UTC)
TAKEOFF = (0.0, 0.0)
LANDING = (100.0, -48.0)
END = _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0)


class Stream:
    """A Session's records, built in time order."""

    def __init__(self) -> None:
        self.records: list[Record] = []
        self.t = 0.0

    def _add(self, event: str, payload: dict, cid: str | None) -> None:
        stamp = EPOCH + datetime.timedelta(seconds=self.t)
        self.records.append(
            Record(len(self.records) + 1, stamp, cid, "t", event, payload, self.t)
        )

    def read(self, x: float, y: float, status: str = "read") -> None:
        self.t += 0.1
        if status == "read":
            self._add(POSITION_READ, {"status": status, "x": x, "y": y}, None)
        else:
            self._add(POSITION_READ, {"status": status, "x": None, "y": None}, None)

    def reads(self, *points: tuple[float, float]) -> None:
        for x, y in points:
            self.read(x, y)

    def settle(self, point: tuple[float, float], n: int = 5) -> None:
        self.reads(*[point] * n)

    def plan(
        self,
        *components: _MovementComponent,
        origin: tuple[float, float] = TAKEOFF,
        cid: str | None = "c",
        legacy: bool = False,
    ) -> None:
        self.t += 0.05
        payload = dict(
            plan_started_payload(
                (*components, END),
                (0, 0),
                (1, 1),
                virtual_position=origin,
                virtual_target=(0, 0),
                scale=16,
            )
        )
        if legacy:
            del payload["transitions"]
        self._add(MOVEMENT_PLAN_STARTED, payload, cid)


def jump(**flags: bool) -> _MovementComponent:
    return _MovementComponent(
        MovementTypes.JUMP_RIGHT,
        100.0,
        duration=0.55,
        start=TAKEOFF,
        end=LANDING,
        **flags,
    )


FLIGHT = ((30.0, -30.0), (70.0, -55.0), (100.0, -48.0))


def land(s: Stream) -> None:
    s.reads(*FLIGHT)
    s.settle(LANDING)


def miss_back_on_takeoff(s: Stream) -> None:
    s.reads((20.0, -30.0), (40.0, -45.0), (60.0, -20.0), (60.0, 0.0))
    s.settle((60.0, 0.0))
    s.reads((30.0, 0.0), (0.0, 0.0), (0.0, 0.0))


def test_one_gesture_across_many_cycles_is_one_attempt() -> None:
    """Delimitation is the gesture, never the cycle (CONTEXT.md)."""
    s = Stream()
    for _ in range(4):  # four re-plans while it walks up
        s.plan(jump(narrow=True))
        s.read(0.0, 0.0)
    land(s)

    [inst] = analyze(s.records).instances

    assert (inst.row, len(inst.attempts), inst.outcome) == ("PM2", 1, "success")
    assert inst.verdict == "pass"
    assert inst.cycles == 4


def test_a_miss_then_a_hit_is_two_attempts_within_the_tight_budget() -> None:
    s = Stream()
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    miss_back_on_takeoff(s)
    s.plan(jump(narrow=True))
    land(s)

    [inst] = analyze(s.records).instances

    assert [a.outcome for a in inst.attempts] == ["missed", "success"]
    assert inst.verdict == "pass"


def test_four_attempts_overrun_the_tight_budget_even_on_a_success() -> None:
    s = Stream()
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    for _ in range(3):
        miss_back_on_takeoff(s)
        s.plan(jump(narrow=True))
    land(s)

    [inst] = analyze(s.records).instances

    assert (len(inst.attempts), inst.outcome, inst.verdict) == (4, "success", "fail")
    assert (inst.tier, inst.budget) == ("Tight", 3)


def test_a_pm3_fall_is_its_own_outcome_and_the_climb_back_belongs_to_no_attempt() -> (
    None
):
    s = Stream()
    s.plan(jump(edge_departure=True))
    s.read(0.0, 0.0)
    s.reads((20.0, -20.0), (40.0, -10.0), (60.0, 60.0), (60.0, 150.0))
    s.settle((60.0, 150.0))
    # Unrelated recovery: walk back and climb to the take-off's height.
    s.plan(_MovementComponent(MovementTypes.CLIMB_UP, 150.0))
    s.reads((40.0, 150.0), (10.0, 100.0), (0.0, 50.0), (0.0, 0.0), (0.0, 0.0))
    s.plan(jump(edge_departure=True))
    land(s)

    [inst] = analyze(s.records).instances

    assert inst.row == "PM3"
    assert [a.outcome for a in inst.attempts] == ["fell", "success"]
    assert inst.fells == 1
    assert inst.verdict == "pass"


def test_a_pm3_instance_that_ends_after_a_fall_is_reported_fell() -> None:
    s = Stream()
    s.plan(jump(edge_departure=True))
    s.read(0.0, 0.0)
    s.reads((20.0, -20.0), (40.0, 20.0), (60.0, 120.0))
    s.settle((60.0, 150.0))

    [inst] = analyze(s.records).instances

    assert (inst.outcome, inst.verdict) == ("fell", "inconclusive")


def test_a_plan_the_character_never_reached_has_no_attempt() -> None:
    s = Stream()
    s.plan(jump(narrow=True), origin=(-500.0, 0.0))
    s.reads((-500.0, 0.0), (-400.0, 0.0))

    [inst] = analyze(s.records).instances

    assert (len(inst.attempts), inst.verdict) == (0, "no_gesture")


def test_a_rope_grab_is_judged_on_the_rope_column() -> None:
    s = Stream()
    rope = _MovementComponent(
        MovementTypes.JUMP,
        0.0,
        duration=0.3,
        start=TAKEOFF,
        end=(0.0, -90.0),
        grabs_rope=True,
    )
    s.plan(rope)
    s.read(0.0, 0.0)
    s.reads((0.0, -30.0), (0.0, -70.0), (0.0, -90.0), (0.0, -110.0), (0.0, -130.0))

    [inst] = analyze(s.records).instances

    assert (inst.row, len(inst.attempts), inst.verdict) == ("PM1", 1, "pass")


def test_a_portal_is_a_discontinuity_and_routine_tier_allows_two() -> None:
    portal = _MovementComponent(
        MovementTypes.ENTER_PORTAL, 0.0, duration=0.1, start=TAKEOFF, end=(900.0, 300.0)
    )
    s = Stream()
    for _ in range(3):  # three presses, no teleport
        s.plan(portal)
        s.settle(TAKEOFF, 4)
        s.t += 1.0
    s.plan(portal)
    s.reads((0.0, 0.0), (900.0, 300.0), (900.0, 300.0), (900.0, 300.0))

    [inst] = analyze(s.records).instances

    assert (inst.row, inst.tier, inst.budget) == ("PM4", "Routine", 2)
    assert (len(inst.attempts), inst.outcome, inst.verdict) == (4, "success", "fail")


def test_a_ladder_grab_after_a_walk_is_pm5() -> None:
    walk = _MovementComponent(
        MovementTypes.WALK_RIGHT, 20.0, start=(-20.0, 0.0), end=TAKEOFF
    )
    climb = _MovementComponent(
        MovementTypes.CLIMB_UP, 90.0, start=TAKEOFF, end=(0.0, -90.0)
    )
    s = Stream()
    s.plan(walk, climb, origin=(-20.0, 0.0))
    s.reads((-20.0, 0.0), (0.0, 0.0))
    s.plan(climb, origin=TAKEOFF)
    s.reads((0.0, 0.0), (0.0, -20.0), (0.0, -40.0), (0.0, -60.0))
    s.settle((0.0, -60.0), 3)

    [inst] = analyze(s.records).instances

    assert (inst.row, inst.verdict) == ("PM5", "pass")


def test_a_success_ends_the_instance() -> None:
    s = Stream()
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    land(s)
    s.reads((50.0, -48.0), (0.0, 0.0), (0.0, 0.0))  # back to the take-off later
    s.t += 5
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    land(s)

    instances = analyze(s.records).instances

    assert [len(i.attempts) for i in instances] == [1, 1]


def test_flags_decide_the_row_and_pm3_outranks_pm2() -> None:
    s = Stream()
    s.plan(jump(narrow=True, edge_departure=True))
    s.read(0.0, 0.0)
    land(s)

    [inst] = analyze(s.records).instances

    assert (inst.row, inst.also) == ("PM3", ("PM2",))


def test_a_plain_jump_is_no_precision_movement() -> None:
    s = Stream()
    s.plan(jump())
    s.read(0.0, 0.0)
    land(s)

    assert analyze(s.records).instances == []


def test_a_cycle_without_transitions_is_counted_not_guessed() -> None:
    s = Stream()
    s.plan(jump(narrow=True), legacy=True)
    s.read(0.0, 0.0)
    land(s)

    result = analyze(s.records)

    assert result.instances == []
    assert result.legacy_cycles == 1


def test_unsure_reads_are_counted_and_never_used() -> None:
    s = Stream()
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    s.read(0.0, 0.0, status="unsure")
    land(s)

    result = analyze(s.records)

    assert result.unsure_reads == 1
    assert result.instances[0].verdict == "pass"


def test_trial_records_are_joined_by_correlation_id(tmp_path: Path) -> None:
    s = Stream()
    s.plan(jump(narrow=True), cid="abc")
    s.read(0.0, 0.0)
    land(s)
    path = tmp_path / "trial.jsonl"
    cycle = CycleRecord(
        "sched",
        "b1",
        "t3",
        "measuring",
        1,
        0.0,
        "now",
        (0, 0),
        (1, 1),
        0.0,
        True,
        correlation_id="abc",
    )
    path.write_text(
        "\n".join(
            json.dumps(r.to_json()) for r in (ScheduleHeader.now("sched", "m"), cycle)
        ),
        encoding="utf-8",
    )

    [inst] = analyze(s.records, trial_cycles([path])).instances

    assert inst.trials == ("sched/b1/t3",)


def test_the_command_line_reads_a_session_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Stream()
    s.plan(jump(narrow=True))
    s.read(0.0, 0.0)
    land(s)
    file = tmp_path / "telemetry.jsonl"
    file.write_text(
        "\n".join(
            json.dumps(
                {
                    "timestamp": r.timestamp.isoformat(),
                    "correlation_id": r.correlation_id,
                    "logger_name": r.logger_name,
                    "event_type": r.event_type,
                    "payload": dict(r.payload),
                }
            )
            for r in s.records
        ),
        encoding="utf-8",
    )

    assert main([str(file), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["instances"][0]["row"] == "PM2"
    assert out["summary"]["verdicts_by_row"] == {"PM2": {"pass": 1}}


def test_a_missing_session_is_exit_2(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2


def test_plan_started_transitions_carry_flags_and_virtual_points() -> None:
    payload = plan_started_payload(
        (jump(narrow=True), _MovementComponent(MovementTypes.WALK_LEFT, 5.0)),
        (0, 0),
        (1, 1),
        virtual_position=(0, 0),
        virtual_target=(1, 1),
        scale=16,
    )

    assert payload["transitions"] == [
        {
            "narrow": True,
            "edge_departure": False,
            "grabs_rope": False,
            "start": [0.0, 0.0],
            "end": [100.0, -48.0],
        },
        {
            "narrow": False,
            "edge_departure": False,
            "grabs_rope": False,
            "start": None,
            "end": None,
        },
    ]
    json.dumps(payload)
