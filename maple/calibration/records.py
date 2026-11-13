"""
Trial records: what actually happened, written as per-machine JSONL.

A record is an **experiment artifact**, not Session telemetry. The distinction is
ownership, and it is load-bearing: `telemetry.jsonl` belongs to the logging map and
describes a Session; a trial record belongs to the movement-calibration map and
describes a Trial. They are joined, not merged - every cycle record carries the
Correlation ID of the `_decide()` call that produced it, which is the key that
reaches the `action.*` records for the same cycle.

That join is also how the *compiled* half of a cycle is reached. Compilation happens
at dispatch, in Main Process, inside the focus lock (ADR 0002); the DecisionMaker
that records the cycle runs in an Engine and cannot see the Input Sequence, let alone
the Delivered Prefix a cancel truncated it to. So `CycleRecord.sequence` is optional:
filled in by an offline compile (`summarize_sequence`) where the framework compiles
for itself, and `None` on the live path, where the Correlation ID stands in for it.

One file per run of a schedule, four kinds of line:

* ``header``  - once, first: which schedule, which map, which machine, when, and
  the physics the sitting planned with.
* ``cycle``   - one per decision cycle.
* ``sample``  - one per position read while an Action is in flight: what the
  analyzer measures the physics from (`maple/calibration/analysis.py`).
* ``outcome`` - one per Trial, after its last cycle.

**Units.** Positions, targets, errors and tolerances are virtual px. A position is
recorded as it was read: its status, and for a read one its source (``fused``
from the play area, ``coarse`` from the minimap alone), so an unsure read is a
line that says so rather than a plausible number (C-NOGUESS). ``frame_time`` is
the read's frame capture time (`time.monotonic()`), the clock the physics are
measured on.

The format round-trips: `read_records(path)` returns exactly what was written, so an
analyzer and the framework never disagree about what a file says.
"""

from __future__ import annotations

import json
import platform
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar, Final, Protocol, Self

from botting.controller import KeyboardInputWrapper
from botting.screen import Reading
from maple.calibration.specs import Knobs
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.screen.position import VirtualPosition
from paths import ROOT

#: Where records land. Gitignored: a record is measured on one machine, by one
#: character, against one client, and means nothing checked in.
RECORDS_DIR: Final = Path(ROOT) / "trial_records"


class Phase(StrEnum):
    """Which half of a Trial a cycle belongs to. Only `MEASURING` is measured."""

    POSITIONING = "positioning"
    MEASURING = "measuring"


class TrialResult(StrEnum):
    """How a Trial ended."""

    #: Reached the target inside tolerance, within budget. The only success.
    ARRIVED = "arrived"
    #: Ran out of time budget still outside tolerance.
    TIMEOUT = "timeout"
    #: Never reached ``start``, so nothing was measured. Not a slow arrival.
    SETUP_FAILED = "setup_failed"
    #: The run was stopped from outside - the schedule was cut short.
    ABANDONED = "abandoned"


# --- Summaries --------------------------------------------------------------------


@dataclass(frozen=True)
class MovementSummary:
    """
    One component of a Movement Plan, reduced to JSON primitives.

    ``length`` is virtual px (`_MovementComponent.length`), rounded to 0.1.
    ``duration`` is the component's own seconds where it sets them (a jump's
    flight, a drop's or a fall's time), which is what the analyzer checks a
    measured flight against; ``start`` and ``end`` are its planned take-off and
    landing, virtual px. All three are `None` where the component has none.
    """

    movement_type: str
    length: float
    narrow: bool
    edge_departure: bool
    duration: float | None = None
    casts: int = 1
    grabs_rope: bool = False
    start: tuple[float, float] | None = None
    end: tuple[float, float] | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.movement_type,
            "length": self.length,
            "narrow": self.narrow,
            "edge_departure": self.edge_departure,
            "duration": self.duration,
            "casts": self.casts,
            "grabs_rope": self.grabs_rope,
            "start": None if self.start is None else list(self.start),
            "end": None if self.end is None else list(self.end),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> MovementSummary:
        duration = payload.get("duration")
        return cls(
            movement_type=str(payload["type"]),
            length=float(payload["length"]),
            narrow=bool(payload["narrow"]),
            edge_departure=bool(payload["edge_departure"]),
            duration=None if duration is None else float(duration),
            casts=int(payload.get("casts", 1)),
            grabs_rope=bool(payload.get("grabs_rope", False)),
            start=_optional_xy(payload.get("start")),
            end=_optional_xy(payload.get("end")),
        )


def summarize_plan(
    movements: tuple[_MovementComponent, ...] | None,
) -> tuple[MovementSummary, ...]:
    """
    A Movement Plan as it goes into a record: type names rather than `IntEnum`
    members, so a record stays readable after the enum's numbering changes.
    """
    if not movements:
        return ()
    return tuple(
        MovementSummary(
            MovementTypes(component.movement_type).name,
            round(float(component.length), 1),
            bool(component.narrow),
            bool(component.edge_departure),
            duration=(
                None if component.duration is None else float(component.duration)
            ),
            casts=int(component.casts),
            grabs_rope=bool(component.grabs_rope),
            start=_rounded_xy(component.start),
            end=_rounded_xy(component.end),
        )
        for component in movements
    )


@dataclass(frozen=True)
class PositionRecord:
    """
    A `Reading[VirtualPosition]` as it goes into a record: the status always, the
    feet and their source only for a read one.

    :ivar status: The reading's status (``read``, ``unsure``, ...).
    :ivar position: The feet, virtual px, rounded to 0.1; `None` unless read.
    :ivar source: ``fused`` or ``coarse``; `None` unless read.
    :ivar frame_time: When the frame it was read from was captured
        (`time.monotonic()`).
    """

    status: str
    position: tuple[float, float] | None
    source: str | None
    frame_time: float

    @property
    def is_read(self) -> bool:
        return self.position is not None

    @classmethod
    def of(cls, reading: Reading[VirtualPosition]) -> PositionRecord:
        value = reading.value
        if value is None:
            return cls(reading.status.value, None, None, float(reading.frame_time))
        return cls(
            reading.status.value,
            (round(float(value.x), 1), round(float(value.y), 1)),
            value.source.value,
            float(reading.frame_time),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "position": None if self.position is None else list(self.position),
            "source": self.source,
            "frame_time": self.frame_time,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> PositionRecord:
        source = payload.get("source")
        return cls(
            status=str(payload["status"]),
            position=_optional_xy(payload.get("position")),
            source=None if source is None else str(source),
            frame_time=float(payload["frame_time"]),
        )


@dataclass(frozen=True)
class SequenceSummary:
    """
    A compiled Input Sequence, reduced to the four things an analyzer asks of it:
    how many Steps, how long, which keys, and what it force-releases at the end.

    Deliberately not the Steps themselves. A record that carried every keystroke
    would duplicate what the movement lab's Goldens already pin offline; what a Trial
    adds is which sequence was chosen *at this position*, not what it expands to.
    """

    step_count: int
    duration: float
    keys: tuple[str, ...]
    forced_releases: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "step_count": self.step_count,
            "duration": self.duration,
            "keys": list(self.keys),
            "forced_releases": list(self.forced_releases),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> SequenceSummary:
        return cls(
            step_count=int(payload["step_count"]),
            duration=float(payload["duration"]),
            keys=tuple(str(key) for key in payload["keys"]),
            forced_releases=tuple(str(key) for key in payload["forced_releases"]),
        )


def summarize_sequence(sequence: KeyboardInputWrapper | None) -> SequenceSummary | None:
    """
    Reduce a compiled Input Sequence to its record form.

    A Step's key may itself be a list (simultaneous presses), so the key list is
    flattened in order - it says which keys the sequence touches and in what order,
    which is what an oscillation left in the record looks like.
    """
    if sequence is None:
        return None
    keys: list[str] = []
    for key in sequence.keys:
        if isinstance(key, list):
            keys.extend(str(k) for k in key)
        else:
            keys.append(str(key))
    return SequenceSummary(
        step_count=len(sequence.keys),
        duration=float(sequence.duration),
        keys=tuple(keys),
        forced_releases=tuple(str(k) for k in sequence.forced_key_releases),
    )


# --- The three record kinds -------------------------------------------------------


@dataclass(frozen=True)
class ScheduleHeader:
    """
    The first line of a file: which experiment this is, and where it was run.

    ``map`` is the schedule's own, a game name or an id; ``map_id`` is what it
    resolved to on the bot's map. The rest is what the analyzer needs to turn
    measured speeds into Calibration constants, which multiply the game-file
    derivations: the `Physics.img` values the sitting planned with
    (``physics``), the character's ``speed_multiplier`` and ``jump_multiplier``,
    and the ``calibration`` constants in force. Each is `None` where the run had
    none to give (an offline run, a test).
    """

    schedule: str
    map: str | int
    started_at: str
    machine: str
    map_id: int | None = None
    physics: dict[str, float] | None = None
    speed_multiplier: float | None = None
    jump_multiplier: float | None = None
    calibration: dict[str, float] | None = None

    kind: ClassVar[str] = "header"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schedule": self.schedule,
            "map": self.map,
            "started_at": self.started_at,
            "machine": self.machine,
            "map_id": self.map_id,
            "physics": self.physics,
            "speed_multiplier": self.speed_multiplier,
            "jump_multiplier": self.jump_multiplier,
            "calibration": self.calibration,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> ScheduleHeader:
        map_setting = payload["map"]
        map_id = payload.get("map_id")
        return cls(
            schedule=str(payload["schedule"]),
            map=map_setting if isinstance(map_setting, int) else str(map_setting),
            started_at=str(payload["started_at"]),
            machine=str(payload["machine"]),
            map_id=None if map_id is None else int(map_id),
            physics=_optional_floats(payload.get("physics")),
            speed_multiplier=_optional_float(payload.get("speed_multiplier")),
            jump_multiplier=_optional_float(payload.get("jump_multiplier")),
            calibration=_optional_floats(payload.get("calibration")),
        )

    @classmethod
    def now(
        cls,
        schedule: str,
        map_setting: str | int,
        *,
        map_id: int | None = None,
        physics: dict[str, float] | None = None,
        speed_multiplier: float | None = None,
        jump_multiplier: float | None = None,
        calibration: dict[str, float] | None = None,
    ) -> Self:
        """A header stamped now, on this machine."""
        return cls(
            schedule,
            map_setting,
            utc_now(),
            platform.node(),
            map_id=map_id,
            physics=physics,
            speed_multiplier=speed_multiplier,
            jump_multiplier=jump_multiplier,
            calibration=calibration,
        )


@dataclass(frozen=True)
class CycleRecord:
    """
    One decision cycle: where the character was, where it was going, and what the
    loop decided to do about it.

    ``dispatched`` separates a cycle that shipped a Movement Plan from one that
    decided it had arrived (or run out of budget) and sent nothing - without it, a
    Trial's last cycle looks like a plan that vanished.

    ``error`` is the distance to ``target`` in virtual px, `None` when the
    position was not read: an unsure cycle is judged on nothing.
    """

    schedule: str
    batch: str
    trial: str
    phase: str
    cycle: int
    elapsed: float
    wall_clock: str
    position: PositionRecord
    target: tuple[int, int]
    error: float | None
    dispatched: bool
    correlation_id: str | None = None
    plan: tuple[MovementSummary, ...] = ()
    sequence: SequenceSummary | None = None

    kind: ClassVar[str] = "cycle"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schedule": self.schedule,
            "batch": self.batch,
            "trial": self.trial,
            "phase": self.phase,
            "cycle": self.cycle,
            "elapsed": self.elapsed,
            "wall_clock": self.wall_clock,
            **self.position.to_json(),
            "target": list(self.target),
            "error": self.error,
            "dispatched": self.dispatched,
            "correlation_id": self.correlation_id,
            "plan": [component.to_json() for component in self.plan],
            "sequence": None if self.sequence is None else self.sequence.to_json(),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> CycleRecord:
        return cls(
            schedule=str(payload["schedule"]),
            batch=str(payload["batch"]),
            trial=str(payload["trial"]),
            phase=str(payload["phase"]),
            cycle=int(payload["cycle"]),
            elapsed=float(payload["elapsed"]),
            wall_clock=str(payload["wall_clock"]),
            position=PositionRecord.from_json(payload),
            target=_point(payload["target"]),
            error=_optional_float(payload["error"]),
            dispatched=bool(payload["dispatched"]),
            correlation_id=payload["correlation_id"],
            plan=tuple(
                MovementSummary.from_json(entry) for entry in payload.get("plan", ())
            ),
            sequence=(
                None
                if payload.get("sequence") is None
                else SequenceSummary.from_json(payload["sequence"])
            ),
        )


@dataclass(frozen=True)
class SampleRecord:
    """
    One position read between decision cycles, while an Action is in flight.

    Not a decision cycle: nothing is judged or dispatched on it, and it counts in
    no outcome. It exists because a decision cycle only comes once an Action has
    finished, so cycles alone never see a jump in the air or a walk at full speed;
    the analyzer measures the physics from these (`maple/calibration/analysis.py`).

    ``correlation_id`` is the cycle's whose Action is in flight, the join key into
    the Session's `action.*` records for it.
    """

    schedule: str
    batch: str
    trial: str
    phase: str
    elapsed: float
    position: PositionRecord
    correlation_id: str | None = None

    kind: ClassVar[str] = "sample"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schedule": self.schedule,
            "batch": self.batch,
            "trial": self.trial,
            "phase": self.phase,
            "elapsed": self.elapsed,
            **self.position.to_json(),
            "correlation_id": self.correlation_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> SampleRecord:
        return cls(
            schedule=str(payload["schedule"]),
            batch=str(payload["batch"]),
            trial=str(payload["trial"]),
            phase=str(payload["phase"]),
            elapsed=float(payload["elapsed"]),
            position=PositionRecord.from_json(payload),
            correlation_id=payload.get("correlation_id"),
        )


@dataclass(frozen=True)
class TrialOutcome:
    """
    One Trial's verdict and its two defect counters.

    Judged on arrival reliability first and time-to-arrival second, per the Trial
    definition in `CONTEXT.md`; ``oscillations`` and ``stuck_events`` are *counted*
    rather than folded into a score, because a Knob setting that arrives reliably by
    oscillating is not the same result as one that arrives straight.

    ``final_error`` is virtual px, from the last cycle whose position was read;
    `None` when no cycle of the Trial read one. ``unsure_cycles`` counts the
    measured cycles whose position was not read, which judged nothing.
    ``failed_move`` is the move a `SETUP_FAILED` gave up on, failed
    `SETUP_MOVE_FAILURES` times (`TrialDriver`); `None` otherwise, and in a
    record written before #509.
    """

    schedule: str
    batch: str
    trial: str
    knobs: Knobs
    start: tuple[int, int]
    target: tuple[int, int]
    tolerance: float
    time_budget: float
    result: str
    final_error: float | None
    time_to_arrival: float | None
    duration: float
    cycles: int
    oscillations: int
    stuck_events: int
    longest_stall: int
    started_at: str
    unsure_cycles: int = 0
    measures: str | None = None
    failed_move: MovementSummary | None = None

    kind: ClassVar[str] = "outcome"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schedule": self.schedule,
            "batch": self.batch,
            "trial": self.trial,
            "knobs": self.knobs.to_json(),
            "start": list(self.start),
            "target": list(self.target),
            "tolerance": self.tolerance,
            "time_budget": self.time_budget,
            "result": self.result,
            "final_error": self.final_error,
            "time_to_arrival": self.time_to_arrival,
            "duration": self.duration,
            "cycles": self.cycles,
            "oscillations": self.oscillations,
            "stuck_events": self.stuck_events,
            "longest_stall": self.longest_stall,
            "started_at": self.started_at,
            "unsure_cycles": self.unsure_cycles,
            "measures": self.measures,
            "failed_move": (
                None if self.failed_move is None else self.failed_move.to_json()
            ),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> TrialOutcome:
        time_to_arrival = payload["time_to_arrival"]
        failed_move = payload.get("failed_move")
        return cls(
            schedule=str(payload["schedule"]),
            batch=str(payload["batch"]),
            trial=str(payload["trial"]),
            knobs=Knobs.from_json(payload["knobs"], "outcome"),
            start=_point(payload["start"]),
            target=_point(payload["target"]),
            tolerance=float(payload["tolerance"]),
            time_budget=float(payload["time_budget"]),
            result=str(payload["result"]),
            final_error=_optional_float(payload["final_error"]),
            time_to_arrival=(
                None if time_to_arrival is None else float(time_to_arrival)
            ),
            duration=float(payload["duration"]),
            cycles=int(payload["cycles"]),
            oscillations=int(payload["oscillations"]),
            stuck_events=int(payload["stuck_events"]),
            longest_stall=int(payload["longest_stall"]),
            started_at=str(payload["started_at"]),
            unsure_cycles=int(payload.get("unsure_cycles", 0)),
            measures=payload.get("measures"),
            failed_move=(
                None if failed_move is None else MovementSummary.from_json(failed_move)
            ),
        )


Record = ScheduleHeader | CycleRecord | SampleRecord | TrialOutcome

_RECORD_KINDS: Final[dict[str, Any]] = {
    ScheduleHeader.kind: ScheduleHeader,
    CycleRecord.kind: CycleRecord,
    SampleRecord.kind: SampleRecord,
    TrialOutcome.kind: TrialOutcome,
}


# --- Sinks ------------------------------------------------------------------------


class RecordSink(Protocol):
    """
    Where a `TrialDriver` puts what it produces.

    A Protocol and not a base class, so the offline framework can collect into a
    list and the live one can append to a file without either knowing the other
    exists. `close` is part of it because whoever owns a run has to end it without
    knowing which kind of sink it was handed.
    """

    def write(self, record: Record) -> None: ...

    def close(self) -> None: ...


class ListSink(list[Record]):
    """A sink that keeps records in memory. What the offline lab drives."""

    def write(self, record: Record) -> None:
        self.append(record)

    def close(self) -> None:
        """Nothing to close. Present so a caller can end a run without asking which
        kind of sink it has."""


class JsonlRecordWriter:
    """
    Append-only JSONL, flushed per line.

    Flushing every line costs nothing at a decision cycle's cadence and buys the
    thing that actually matters here: a Session killed mid-schedule - which is how a
    calibration sitting usually ends - leaves a readable file of everything up to
    that point rather than an empty one.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def write(self, record: Record) -> None:
        self._handle.write(json.dumps(record.to_json()) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


# --- Reading back -----------------------------------------------------------------


def read_records(path: Path) -> list[Record]:
    """Every record in a file, in order, as the objects that were written."""
    return list(iter_records(path))


def iter_records(path: Path) -> Iterator[Record]:
    """
    Stream a file's records.

    A blank line is skipped (a file appended to twice can carry one); an unknown
    ``kind`` raises, because silently dropping a record kind an analyzer does not
    know about is how a defect counter goes missing without anyone noticing.
    """
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            kind = payload.get("kind")
            record_cls = _RECORD_KINDS.get(kind)
            if record_cls is None:
                raise ValueError(
                    f"{path}:{number} has unknown record kind {kind!r}. "
                    f"Known kinds: {', '.join(sorted(_RECORD_KINDS))}."
                )
            yield record_cls.from_json(payload)


# --- Helpers ----------------------------------------------------------------------


def utc_now() -> str:
    """The one timestamp format records use: ISO-8601, UTC, seconds resolution."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def default_record_path(
    schedule: str, directory: Path | None = None, when: datetime | None = None
) -> Path:
    """
    Where a run of ``schedule`` writes by default: one file per sitting, named so
    that a directory listing sorts chronologically.
    """
    root = RECORDS_DIR if directory is None else directory
    stamp = (when or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return root / f"{stamp}-{schedule}.jsonl"


def _point(value: list[Any]) -> tuple[int, int]:
    return int(value[0]), int(value[1])


def _optional_xy(value: list[Any] | None) -> tuple[float, float] | None:
    return None if value is None else (float(value[0]), float(value[1]))


def _rounded_xy(value: tuple[float, float] | None) -> tuple[float, float] | None:
    if value is None:
        return None
    return round(float(value[0]), 1), round(float(value[1]), 1)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _optional_floats(value: dict[str, Any] | None) -> dict[str, float] | None:
    if value is None:
        return None
    return {str(key): float(number) for key, number in value.items()}
