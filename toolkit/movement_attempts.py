"""
Attempts from telemetry (#12, epic #302 T32): how many Attempts each Precision
movement took, and whether that is within its Attempt budget. Offline, and it
sends nothing.

    python -m toolkit.movement_attempts logs/2026-11-10_14-02-11
    python -m toolkit.movement_attempts <session dir or telemetry.jsonl> --trials trial_records/x.jsonl --json

**What it reads.** A Session's ``telemetry.jsonl`` and, optionally, Trial
records. From the Session it takes two Event Types and no others:
``movement.plan_started`` (each cycle's Movement Plan, with every component's
precision flags and virtual take-off and landing: ``transitions``) and
``position.read`` (the virtual position, ``read`` ones only; an ``unsure`` read
says nothing and is counted, never used). A cycle recorded before #12 has no
``transitions``: it is skipped and counted, because the flags are not
re-derivable offline (the taxonomy: "do not re-derive edge/narrow geometry").

**Instance.** The same transition seen across cycles: the same component type,
a landing within ``KEY_LANDING_TOL`` and a take-off within ``KEY_TAKEOFF_TOL``
of the first one's, with no more than ``INSTANCE_GAP`` seconds between two
cycles that carry it. It ends at its first success: the next cycle carrying the
transition starts a new instance. A transition's row is the first that applies,
in the taxonomy's priority order PM3, PM2, PM1, PM4, PM5; the others are
reported as ``also``.

**Attempt.** "One delivered gesture aimed at a single precision movement", found
in the position history, never by cycle (CONTEXT.md § Movement attempts):

- PM1, PM2, PM3 (a jump, a drop, a teleport): a *departure*. The character was
  at the take-off (within ``ZONE_X`` along x, ``GROUND_Y`` in y), and a later
  read is more than ``LIFT_Y`` off the take-off's height, or a read-to-read step
  of ``TELEPORT_STEP`` or more starts there (a teleport). The next Attempt is
  the next departure after the character settles and is back at the take-off, so
  the climb back after a fall between two Attempts belongs to neither.
- PM4, PM5 (a portal, a ladder grab from a walk): there is no departure to see
  before the result, so an Attempt is a cycle whose plan starts within
  ``REACH`` of the take-off, once the previous Attempt resolved.

**Success per row**, from positions in the window after the gesture (it closes
at the first ``SETTLE_READS`` reads that stay within ``SETTLE_BOX``, or after
``OUTCOME_WINDOW`` seconds):

- PM1: a read within ``ROPE_X`` of the landing's x and ``ROPE_Y`` of its y.
- PM2 and PM3: a read within ``LAND_X``/``LAND_Y`` of the landing that the
  window's last read is still within ``STAY_X``/``STAY_Y`` of ("remains on it").
- PM3's miss is **fell** when the window ends more than ``FALL_DROP`` below both
  the take-off and the landing; any other miss is **missed**.
- PM4: a read within ``LAND_X``/``LAND_Y`` of the landing, or a step of
  ``PORTAL_STEP`` or more away from the take-off (a portal's discontinuity).
- PM5: a read more than ``LIFT_Y`` off the take-off's height, within ``ROPE_X``
  of its x: vertical movement begins on the ladder column.

**Budget verdict**, from the taxonomy's table: *pass* is a success within the
budget; *fail* is more Attempts than the budget (a success after it, or none);
*inconclusive* is no success yet, within budget; *no_gesture* is an instance
that never saw an Attempt (the plan changed before the character got there).
The budget is an Expectation reported here, never a gate.

**Every number above is an Expectation**, read off no client: they are named so
the first Test Session (#400) can say which one was wrong. What this cannot
decide offline is whether its instances match what a person watching counts.

**Trial records are joined, never merged** (CONTEXT.md): ``--trials`` reads
them, and an instance whose cycles carry a Correlation ID found in a Trial
record's cycles lists that Trial (``schedule/batch/trial``).

**The Delivered Prefix.** A Trial record does **not** carry it. Counting
Attempts needs where the character was, which is the position history; the
Delivered Prefix says which Steps the client got, which is no more than that
history already shows of a gesture, and the compiled half stays reachable
through the Correlation ID (`maple/calibration/records.py`). Carrying it would
need the Step count, which the Delivery Gate keeps in the rotation, written into
a record the Trial framework owns, for no question the analyzer asks.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from botting.session.reading import SessionError, load_session, telemetry_path
from maple.calibration.records import CycleRecord, read_records
from maple.telemetry_events import MOVEMENT_PLAN_STARTED, POSITION_READ

Point = tuple[float, float]

# --- the taxonomy's table (docs/planning/precision-movement-taxonomy.md) -------

#: Row -> (tier, Attempt budget). Revising a budget is editing the taxonomy and
#: this table, nothing else.
BUDGETS: Final[Mapping[str, tuple[str, int]]] = {
    "PM1": ("Tight", 3),
    "PM2": ("Tight", 3),
    "PM3": ("Tight", 3),
    "PM4": ("Routine", 2),
    "PM5": ("Routine", 2),
}
#: The order a transition that fits several rows is filed under.
PRIORITY: Final = ("PM3", "PM2", "PM1", "PM4", "PM5")

# --- Expectations: virtual px and seconds, unmeasured --------------------------

#: Two cycles' transitions are one instance within these of the first one's.
KEY_LANDING_TOL: Final = 16.0
KEY_TAKEOFF_TOL: Final = 96.0
#: Seconds without a cycle carrying a transition before the instance is over.
INSTANCE_GAP: Final = 30.0
#: At the take-off: along x, and in y.
ZONE_X: Final = 96.0
GROUND_Y: Final = 10.0
#: How far off the take-off's height a read is once the character has left it.
LIFT_Y: Final = 12.0
#: A read-to-read step this long, from the take-off, is a teleport or a portal.
TELEPORT_STEP: Final = 120.0
PORTAL_STEP: Final = 200.0
#: A cycle's plan starts "at" a take-off within this (PM4, PM5).
REACH_X: Final = 24.0
REACH_Y: Final = 16.0
#: Landing tolerances, and how far a read may wander and still "remain on it".
LAND_X: Final = 24.0
LAND_Y: Final = 16.0
STAY_X: Final = 32.0
STAY_Y: Final = 16.0
#: A rope's column and the stretch of it a grab can land on.
ROPE_X: Final = 12.0
ROPE_Y: Final = 48.0
#: The window closes on this many reads within this box, or on the clock.
SETTLE_READS: Final = 3
SETTLE_BOX: Final = 6.0
OUTCOME_WINDOW: Final = 4.0
#: Below both the take-off and the landing by this much, and the character fell.
FALL_DROP: Final = 24.0

SUCCESS: Final = "success"
MISSED: Final = "missed"
FELL: Final = "fell"


@dataclass(frozen=True)
class Transition:
    """One precision component of one cycle's Movement Plan."""

    t: float
    correlation_id: str | None
    kind: str
    rows: tuple[str, ...]
    takeoff: Point
    landing: Point
    origin: Point
    flags: tuple[bool, bool, bool]  # narrow, edge_departure, grabs_rope


@dataclass(frozen=True)
class Read:
    t: float
    x: float
    y: float


@dataclass(frozen=True)
class AttemptReport:
    t: float
    outcome: str


@dataclass
class InstanceReport:
    row: str
    also: tuple[str, ...]
    kind: str
    takeoff: Point
    landing: Point
    first_t: float
    last_t: float
    attempts: list[AttemptReport] = field(default_factory=list)
    cycles: int = 0
    outcome: str = "no_gesture"
    tier: str = ""
    budget: int = 0
    verdict: str = "no_gesture"
    correlation_ids: tuple[str, ...] = ()
    trials: tuple[str, ...] = ()

    @property
    def fells(self) -> int:
        return sum(1 for a in self.attempts if a.outcome == FELL)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["attempt_count"] = len(self.attempts)
        out["fells"] = self.fells
        return out


@dataclass
class Analysis:
    instances: list[InstanceReport]
    cycles: int = 0
    legacy_cycles: int = 0
    reads: int = 0
    unsure_reads: int = 0

    def summary(self) -> dict[str, Any]:
        rows: dict[str, Counter[str]] = {}
        for inst in self.instances:
            rows.setdefault(inst.row, Counter())[inst.verdict] += 1
        return {
            "plan_cycles": self.cycles,
            "cycles_without_transitions": self.legacy_cycles,
            "position_reads": self.reads,
            "unsure_reads": self.unsure_reads,
            "instances": len(self.instances),
            "verdicts_by_row": {k: dict(v) for k, v in sorted(rows.items())},
        }


# --- reading the stream ---------------------------------------------------------


def classify(kind: str, flags: tuple[bool, bool, bool], after_walk: bool) -> list[str]:
    """The rows a component is, in priority order."""
    narrow, edge, rope = flags
    jump = kind in ("JUMP", "JUMP_LEFT", "JUMP_RIGHT")
    sideways = kind in ("JUMP_LEFT", "JUMP_RIGHT", "TELEPORT_LEFT", "TELEPORT_RIGHT")
    gesture = jump or kind.startswith("TELEPORT_") or kind == "JUMP_DOWN"
    rows = []
    if sideways and edge:
        rows.append("PM3")
    if gesture and narrow:
        rows.append("PM2")
    if jump and rope:
        rows.append("PM1")
    if kind == "ENTER_PORTAL":
        rows.append("PM4")
    if kind in ("CLIMB_UP", "CLIMB_DOWN") and after_walk:
        rows.append("PM5")
    return rows


def _point(value: Any) -> Point | None:
    if isinstance(value, Sequence) and len(value) >= 2:
        return (float(value[0]), float(value[1]))
    return None


def extract(records: Iterable[Any]) -> tuple[list[Transition], list[Read], Analysis]:
    """The Session's precision transitions and position reads, in time order."""
    transitions: list[Transition] = []
    reads: list[Read] = []
    stats = Analysis([])
    for record in records:
        payload = record.payload
        if record.event_type == POSITION_READ:
            if payload.get("status") == "read" and payload.get("x") is not None:
                reads.append(Read(record.t, float(payload["x"]), float(payload["y"])))
            else:
                stats.unsure_reads += 1
        elif record.event_type == MOVEMENT_PLAN_STARTED:
            stats.cycles += 1
            entries = payload.get("transitions")
            names = [c[0] for c in payload.get("components_v", ())]
            if not entries or len(entries) != len(names):
                stats.legacy_cycles += 1
                continue
            origin = (float(payload["from_vx"]), float(payload["from_vy"]))
            for i, (name, entry) in enumerate(zip(names, entries, strict=True)):
                flags = (
                    bool(entry.get("narrow")),
                    bool(entry.get("edge_departure")),
                    bool(entry.get("grabs_rope")),
                )
                after_walk = i > 0 and names[i - 1].startswith("WALK_")
                rows = classify(name, flags, after_walk)
                start, end = _point(entry.get("start")), _point(entry.get("end"))
                if rows and start is not None and end is not None:
                    transitions.append(
                        Transition(
                            record.t,
                            record.correlation_id,
                            name,
                            tuple(sorted(rows, key=PRIORITY.index)),
                            start,
                            end,
                            origin,
                            flags,
                        )
                    )
    stats.reads = len(reads)
    reads.sort(key=lambda r: r.t)
    return transitions, reads, stats


# --- instances ------------------------------------------------------------------


def _same(first: Transition, other: Transition) -> bool:
    return (
        first.kind == other.kind
        and math.dist(first.landing, other.landing) <= KEY_LANDING_TOL
        and math.dist(first.takeoff, other.takeoff) <= KEY_TAKEOFF_TOL
    )


def group(transitions: Sequence[Transition]) -> list[list[Transition]]:
    """Cycles' transitions, grouped into candidate instances (before success)."""
    groups: list[list[Transition]] = []
    for transition in sorted(transitions, key=lambda x: x.t):
        for candidate in reversed(groups):
            if (
                _same(candidate[0], transition)
                and transition.t - candidate[-1].t <= INSTANCE_GAP
            ):
                # One transition appears once per cycle; a plan may list the
                # same one twice (a retried move): one per cycle is enough.
                if transition.t != candidate[-1].t:
                    candidate.append(transition)
                break
        else:
            groups.append([transition])
    return groups


def _window_end(reads: Sequence[Read], start: int, until: float = math.inf) -> int:
    """
    The index of the last read of the window opened at ``start``: it closes on
    settling, after ``OUTCOME_WINDOW`` seconds, or before time ``until``.
    """
    run = 1
    for j in range(start + 1, len(reads)):
        if reads[j].t - reads[start].t > OUTCOME_WINDOW or reads[j].t >= until:
            return j - 1
        same = (
            abs(reads[j].x - reads[j - 1].x) <= SETTLE_BOX
            and abs(reads[j].y - reads[j - 1].y) <= SETTLE_BOX
        )
        run = run + 1 if same else 1
        if run >= SETTLE_READS and j > start + SETTLE_READS:
            return j
    return len(reads) - 1


def _near(read: Read, point: Point, tx: float, ty: float) -> bool:
    return abs(read.x - point[0]) <= tx and abs(read.y - point[1]) <= ty


def _result(
    row: str, lead: Transition, window: Sequence[Read], t0: float
) -> tuple[str, bool]:
    """(outcome, success) of the gesture made at the start of ``window``."""
    takeoff, landing = lead.takeoff, lead.landing
    if row == "PM1":
        hit = any(_near(r, landing, ROPE_X, ROPE_Y) for r in window)
    elif row == "PM5":
        hit = any(
            abs(r.x - takeoff[0]) <= ROPE_X and abs(r.y - takeoff[1]) > LIFT_Y
            for r in window
        )
    elif row == "PM4":
        hit = any(_near(r, landing, LAND_X, LAND_Y) for r in window) or any(
            math.dist((a.x, a.y), (b.x, b.y)) >= PORTAL_STEP
            for a, b in pairwise(window)
        )
    else:
        hit = any(_near(r, landing, LAND_X, LAND_Y) for r in window) and _near(
            window[-1], landing, STAY_X, STAY_Y
        )
    if hit:
        return SUCCESS, True
    if row == "PM3" and window[-1].y > max(takeoff[1], landing[1]) + FALL_DROP:
        return FELL, False
    return MISSED, False


def _attempts(
    row: str, cycles: Sequence[Transition], reads: Sequence[Read], horizon: float
) -> tuple[list[AttemptReport], float | None]:
    """The Attempts at one instance, and the time of its success, if any."""
    lead = cycles[0]
    out: list[AttemptReport] = []
    if row in ("PM4", "PM5"):
        resume = -math.inf
        for k, cycle in enumerate(cycles):
            if cycle.t < resume or not (
                abs(cycle.origin[0] - cycle.takeoff[0]) <= REACH_X
                and abs(cycle.origin[1] - cycle.takeoff[1]) <= REACH_Y
            ):
                continue
            start = next((i for i, r in enumerate(reads) if r.t >= cycle.t), None)
            if start is None:
                break
            # A cycle's press is judged before the next cycle's: the next one
            # re-plans the same press if it is still at the take-off.
            until = cycles[k + 1].t if k + 1 < len(cycles) else math.inf
            end = _window_end(reads, start, until)
            outcome, ok = _result(row, lead, reads[start : end + 1], cycle.t)
            out.append(AttemptReport(cycle.t, outcome))
            if ok:
                return out, reads[end].t
            resume = reads[end].t
        return out, None

    armed = False
    i = next((k for k, r in enumerate(reads) if r.t >= lead.t), len(reads))
    while i < len(reads) and reads[i].t <= horizon:
        r = reads[i]
        at_takeoff = _near(r, lead.takeoff, ZONE_X, GROUND_Y)
        stepped = (
            armed
            and i > 0
            and lead.kind.startswith("TELEPORT_")
            and math.dist((reads[i - 1].x, reads[i - 1].y), (r.x, r.y)) >= TELEPORT_STEP
        )
        lifted = (
            armed
            and abs(r.y - lead.takeoff[1]) > LIFT_Y
            and abs(r.x - lead.takeoff[0])
            <= ZONE_X + abs(lead.landing[0] - lead.takeoff[0])
        )
        if at_takeoff and not stepped:
            armed = True
            i += 1
            continue
        if not (stepped or lifted):
            i += 1
            continue
        end = _window_end(reads, i)
        outcome, ok = _result(row, lead, reads[i : end + 1], r.t)
        out.append(AttemptReport(r.t, outcome))
        if ok:
            return out, reads[end].t
        armed = False
        i = end + 1
    return out, None


def _judge(inst: InstanceReport, success: bool) -> None:
    inst.tier, inst.budget = BUDGETS[inst.row]
    n = len(inst.attempts)
    if n == 0:
        inst.outcome, inst.verdict = "no_gesture", "no_gesture"
    elif success:
        inst.outcome = SUCCESS
        inst.verdict = "pass" if n <= inst.budget else "fail"
    else:
        inst.outcome = inst.attempts[-1].outcome
        inst.verdict = "fail" if n > inst.budget else "inconclusive"


def analyze(
    records: Iterable[Any], trial_cycles: Mapping[str, str] | None = None
) -> Analysis:
    """
    Every precision-movement instance in a Session's records, with its Attempts.

    :param records: ``botting.session.reading.Record``s, with their clock set.
    :param trial_cycles: Correlation ID -> ``schedule/batch/trial``, from Trial
        records.
    """
    transitions, reads, analysis = extract(records)
    pending = group(transitions)
    while pending:
        cycles = pending.pop(0)
        row = cycles[0].rows[0]
        horizon = cycles[-1].t + OUTCOME_WINDOW
        attempts, won_at = _attempts(row, cycles, reads, horizon)
        if won_at is not None:
            # The instance ends at its success; later cycles are a new one.
            later = [c for c in cycles if c.t > won_at]
            cycles = [c for c in cycles if c.t <= won_at]
            if later:
                pending.insert(0, later)
        ids = tuple(sorted({c.correlation_id for c in cycles if c.correlation_id}))
        inst = InstanceReport(
            row=row,
            also=cycles[0].rows[1:],
            kind=cycles[0].kind,
            takeoff=cycles[0].takeoff,
            landing=cycles[0].landing,
            first_t=cycles[0].t,
            last_t=cycles[-1].t,
            attempts=attempts,
            cycles=len(cycles),
            correlation_ids=ids,
            trials=tuple(
                sorted(
                    {trial_cycles[i] for i in ids if trial_cycles and i in trial_cycles}
                )
            ),
        )
        _judge(inst, won_at is not None)
        analysis.instances.append(inst)
    analysis.instances.sort(key=lambda i: i.first_t)
    return analysis


def trial_cycles(paths: Iterable[Path]) -> dict[str, str]:
    """Correlation ID -> ``schedule/batch/trial`` over Trial record files."""
    joined: dict[str, str] = {}
    for path in paths:
        for record in read_records(path):
            if isinstance(record, CycleRecord) and record.correlation_id:
                joined[record.correlation_id] = (
                    f"{record.schedule}/{record.batch}/{record.trial}"
                )
    return joined


# --- command line ---------------------------------------------------------------


def format_report(analysis: Analysis) -> str:
    lines = [
        (
            f"{'t':>8}  {'row':<4} {'move':<14} {'attempts':>8}  {'outcome':<10} "
            f"{'budget':<9} verdict"
        )
    ]
    for inst in analysis.instances:
        fell = f" ({inst.fells} fell)" if inst.fells else ""
        lines.append(
            f"{inst.first_t:8.1f}  {inst.row:<4} {inst.kind:<14} "
            f"{len(inst.attempts):>8}  {inst.outcome:<10} "
            f"{inst.tier + ' ' + str(inst.budget):<9} {inst.verdict}{fell}"
        )
    lines.append(json.dumps(analysis.summary()))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("session", nargs="?", type=Path, help="Session dir or file")
    parser.add_argument("--trials", nargs="*", type=Path, default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        session = load_session(telemetry_path(args.session))
    except SessionError as error:
        print(error, file=sys.stderr)
        return 2
    analysis = analyze(session.records, trial_cycles(args.trials))
    if args.json:
        print(
            json.dumps(
                {
                    "summary": analysis.summary(),
                    "instances": [i.to_json() for i in analysis.instances],
                }
            )
        )
    else:
        print(format_report(analysis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
