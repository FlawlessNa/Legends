"""
Per-move accuracy report for a Trial: planned against actual, key times, retries, loop timing.

Offline. It reads a Trial record and, optionally, the Session that ran it,
writes a Markdown report and a PNG route plot, and sends nothing and reads
nothing from the game (#536, epic #302).

    python -m toolkit.trial_report trial_records/x.jsonl logs/<session dir>
    python -m toolkit.trial_report run27.jsonl run27_session --compare run25.jsonl
    python -m toolkit.trial_report run27.jsonl run27_session --moment 08:33:20

``--out`` names the report (default: next to the record, ``<record>.report.md``,
with ``<record>.route.png``). ``--compare`` takes more records (each optionally
``record.jsonl=session_dir``) for a side-by-side of the same route. ``--moment``
(repeatable) is a moment someone saw go wrong, as ``HH:MM:SS`` (local time, as
the Session logs it; the record's UTC ``wall_clock`` when no Session is given)
or ``trial@seconds`` (seconds into the Trial's measured phase); the report
lists the moves around it and says whether it flagged one.

**What it reads.** From the record (`maple.calibration.records`): each measured
cycle's read and Movement Plan (every component's planned ``start`` and
``end``, virtual px) and every sample read. From the Session, when given:
``telemetry.jsonl``'s ``action.scheduled`` and ``action.finished`` (joined to a
cycle by Correlation ID), ``key.down`` and ``key.up`` (#538: each key's
transition, by the Correlation ID of the Action that sent it, its ``t`` on
``time.monotonic()``, the record's own clock, so it needs no offset) and
``position.read``, and ``session.log``'s ``Computing path`` and ``Movements``
lines (planning).

**The Session's clock on the record's.** A key record carries both clocks of
one send, ``wall`` (epoch) and ``t`` (``time.monotonic()``, the record's): the
offset is their median difference, exact to the microsecond (#540). A Session
from before #538 has none, and each ``position.read`` event is matched to the
record line with the same position instead, the offset their median
difference. That event is written once the read is done, not when its frame
was captured, so that offset is late by the read's own time: on run 28, 119
ms, by which every Session time (schedule, finish, planning) sat early on the
record's clock, the read ages short and the loop's wait long. With key records,
the report gives that read time (``position.read`` after its frame's capture).
Nothing from either is copied into the report but positions, times, key names
and move types: no player name, no window title, no machine name.

**The judged move.** Each cycle runs at most one Action, cut at the Action
duration cap (1 s by default), so it reaches only the start of its Plan. Its
Plan's components are merged (consecutive walks or climbs the same way are one
move), and the cycle is judged on its first move that is not a walk, the
**key move**, when the samples show its take-off or when the walk before it is
no longer than one cut's reach (walk speed times the cap). Otherwise the cycle
is an approach, judged as a walk. The window of reads judged runs from the
cycle's read to the read of the next cycle that has a Plan (cycles with none,
read in the air or off any platform, are part of the window).

**Verdicts, and how each is decided** (every threshold is an Expectation, named
below, read off no client):

- *Take-off* (jumps, drops, flash jumps). The take-off is the first read more
  than ``LIFT_Y`` off the planned take-off height whose previous read was on it
  (within ``GROUND_Y``) and within ``ZONE_X`` of the take-off x. The two reads
  bracket the real take-off: **early** when the first read in the air is still
  more than ``TAKEOFF_SLACK`` short of the planned take-off x, in the direction
  of travel; **late** when the last read on the ground is already more than
  that past it; else on time. A vertical move (a jump straight up, a drop) has
  no early or late.
- *Landing*. The landing is the first read after the take-off that the next read
  stays within ``SETTLE_DY`` of in y (standing, or hanging on a rope), else the
  window's last read. Its error vector is landing minus planned end, px (y
  grows downward). **ok** within ``LAND_X`` and ``LAND_Y`` (a rope grab: within
  ``ROPE_X`` of the rope's x); **short** or **long** (overshoot) on the planned
  height but off along the travel direction (a drop that stayed up is short);
  **fell** more than ``FALL_DROP`` below both the take-off and the planned end;
  **off** anywhere else.
- **no take-off**: the key move was in reach, the character got to its
  take-off, and no read left the ground. **not reached**: in reach, but the
  window ended short of the take-off.
- *Walk* (an approach whose end is in reach, or a Plan of walks only): the stop
  is the window's last read, error along the walk's direction: ok within
  ``LAND_X``, else short or long. A walk longer than a cut's reach is **en
  route**, judged on nothing. A climb is ok when a read reaches its end, else
  en route; a portal is ok when a read lands within ``LAND_X`` of its exit or
  steps ``PORTAL_STEP`` or more.
- **retried**: the move belongs to a cluster.

**At the key** (a Session with ``key.down``/``key.up``; older Sessions keep the
verdicts above). The key's time is placed on the reads: the x then is
interpolated between the two reads around it, so a key time is judged to the
read's precision in x, not to the sample spacing.

- *Take-off* (a jump or drop the reads saw leave the ground): the take-off key
  is the Action's first ``key.down`` that is not a direction key, from one of
  the move's Plan components when the records carry their Provenance
  (``origin``). Its x against the planned take-off x: **early** more than
  ``TAKEOFF_SLACK`` short, **late** more than that past, in px and in ms at the
  walk speed; a vertical move is **on spot** within ``LAND_X``, else **off
  spot**. This replaces the bracket's take-off, which is still shown.
- *Walk stop* (a walk judged on its stop): the walk's direction key's first
  ``key.up`` in the Action. Where the character comes to rest from there (the x
  at the key, plus the slide from the speed the reads give then,
  ``v² / 2 deceleration``, ``walkDrag`` over the mass) against the planned end:
  **ok** within ``LAND_X``, else **long** or **short**, in px and in ms at the
  walk speed. When the last read says otherwise, both are given
  (``ok, stopped long``). A walk whose key stays down across the cut (a
  Continuation) has no ``key.up`` in its Action and keeps the read's verdict.

**The limit** is the sample spacing (median about 0.25 s on run 27, 0.12 s on
reads alone): a take-off is bracketed between two reads up to one spacing
apart, so early or late is only said beyond the bracket, and a landing read can
be one spacing after the touch-down. A jump's apex can pass for a landing when
two reads straddle it at the same height. A coarse read (the minimap alone) is
16 px wide and is judged like a fused one. At the key, the limit is the
interpolation: a read every 0.12 to 0.25 s at walk speed is 15 to 37 px apart,
and a speed change between the two reads (the walk accelerating, the slide)
bends the line the x is read off. The key time itself is ``SendInput``'s
return; the client acts on it at its next frame.

**Clusters.** Consecutive cycles (skipping cycles with no Plan) whose key move
is the same move: the same kind, a planned end within ``KEY_X`` and ``KEY_Y``
(``KEY_ROPE_Y`` in y for a rope grab, whose height may move along the rope). A
cluster is reported when it holds two **tries** or more, a try being a cycle
judged on that move that took off (or, for a portal or climb, was in reach).
Seconds lost: from the first try to the last try's start, what the repeats
cost. It leaves out the last try's own time, so when the last try missed too,
the real loss is larger. The tries' landing offsets along the travel direction
give the hypothesis: the same side every time, growing, early or late take-offs.

**Loop timing** (with a Session). Per cycle: the read's age when planning began
and when the Action was scheduled; planning (``Computing path`` to its
``Movements`` line); hand-off (that line to ``action.scheduled``: the pipe to
Main Process and `AsyncTaskManager`'s own throttle); the Action's length and
why it ended (``cut`` within ``CUT_TOL`` of the cap, ``past cut`` when the
compile finished a walk or a jump beyond it (#503, #515), ``plan end`` short of
it); and the gap from the previous Action's finish to this one's schedule,
split into the loop's wait (finish to the first capture after it; negative
when the cycle planned on a frame captured before the finish, a stale frame),
cycles with no Plan, read and planning, and hand-off. Schedule to first key:
``action.scheduled`` to the Action's first ``key.down`` or ``key.up``, both on
Main Process's wall clock (the focus lock, the dispatch-time compile and the
first ``SendInput``), in a Session that has them.

**Where the time goes** names the settings from the code, with their values, and
ranks the options for the maintainer; this tool changes none of them.
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, tzinfo
from itertools import pairwise
from pathlib import Path
from typing import Final

from maple.calibration.records import (
    CycleRecord,
    MovementSummary,
    Phase,
    Record,
    SampleRecord,
    ScheduleHeader,
    TrialOutcome,
    one_per_frame,
    read_records,
)
from maple.model.mechanics.physics import CHARACTER_MASS

# --- Expectations (read off no client; named so a live check can say which) ------

#: Virtual px off the take-off height that says the character has left it.
LIFT_Y: Final = 8.0
#: Virtual px from the take-off height a read stands within to be on it.
GROUND_Y: Final = 12.0
#: The last read on the ground is within this of the take-off x (virtual px).
ZONE_X: Final = 80.0
#: Past the bracket by more than this (virtual px) is early or late.
TAKEOFF_SLACK: Final = 6.0
#: A landing within these of the planned end is ok (virtual px).
LAND_X: Final = 20.0
LAND_Y: Final = 10.0
#: A rope grab is ok within this of the rope's x (virtual px).
ROPE_X: Final = 8.0
#: Seconds: no jump rises this long (`Physics.img` jumpSpeed 555 over
#: gravityAcc 2000 is 0.28 s), so rising for longer on one column is a climb.
RISE_MAX: Final = 0.45
#: Virtual px/s: faster than this along a column is a fall, not a climb
#: (a climb measured about 100 to 140, `Physics.img` fallSpeed is 670).
CLIMB_MAX: Final = 300.0
#: Below both the take-off and the planned end by more than this is a fall.
FALL_DROP: Final = 30.0
#: Three consecutive reads within this in y: standing or hanging (virtual px).
SETTLE_DY: Final = 4.0
#: A read-to-read step this long is a portal (virtual px).
PORTAL_STEP: Final = 200.0
#: Two key moves are the same move: planned ends this close (virtual px).
KEY_X: Final = 12.0
KEY_Y: Final = 12.0
KEY_ROPE_Y: Final = 60.0
#: An Action this close to the cap (s) ended on the cut.
CUT_TOL: Final = 0.04
#: `TrialRunner.DEFAULT_ACTION_DURATION`: the cap when the batch sets no
#: ``action_duration`` Knob. A test pins the two together.
DEFAULT_CUT: Final = 1.0
#: The settings "Where the time goes" names, with their values in the code; a
#: test pins each to its source. `TrialRunner._throttle`, the decision loop's
#: period (the ``decision_interval`` Knob's default):
LOOP_PERIOD: Final = 0.1
#: `AsyncTaskManager._throttle`, Main Process's sleep before each queue read:
HANDOFF_THROTTLE: Final = 0.1
#: The ``current_frame`` refresh threshold, `ClientProvider.FRAME_REFRESH`:
FRAME_CACHE: Final = 0.1
#: `Physics.img` walkSpeed, when the header carries no physics.
DEFAULT_WALK_SPEED: Final = 125.0
#: Fewer than this in a group, and a comparison says the sample is too small.
SMALL: Final = 5

_WALKS: Final = {"WALK_LEFT", "WALK_RIGHT"}
_CLIMBS: Final = {"CLIMB_UP", "CLIMB_DOWN"}
_KIND: Final = {
    "WALK_LEFT": "walk",
    "WALK_RIGHT": "walk",
    "CLIMB_UP": "climb",
    "CLIMB_DOWN": "climb",
    "JUMP": "jump",
    "JUMP_LEFT": "jump",
    "JUMP_RIGHT": "jump",
    "FLASH_JUMP_LEFT": "jump",
    "FLASH_JUMP_RIGHT": "jump",
    "JUMP_DOWN": "drop",
    "ENTER_PORTAL": "portal",
    "TELEPORT_LEFT": "teleport",
    "TELEPORT_RIGHT": "teleport",
    "TELEPORT_UP": "teleport",
    "TELEPORT_DOWN": "teleport",
}
#: Verdicts that are a miss: the move did not do what was planned.
MISSES: Final = frozenset(
    {"short", "long", "fell", "off", "no take-off", "not reached"}
)

Point = tuple[float, float]


# --- the record -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Read:
    """One read position: its frame's capture time (record clock) and feet."""

    t: float
    x: float
    y: float
    source: str | None = None


@dataclass(frozen=True)
class Move:
    """One move of a Plan, after merging same-way walks and climbs."""

    type: str
    start: Point
    end: Point
    length: float
    duration: float | None = None
    grabs_rope: bool = False
    #: The indices, in the cycle's Plan, of the components merged into this move:
    #: what a key record's ``origin`` (its Provenance) is matched against.
    components: tuple[int, ...] = ()

    @property
    def kind(self) -> str:
        return _KIND.get(self.type, self.type.lower())

    @property
    def direction(self) -> int:
        dx = self.end[0] - self.start[0]
        return 0 if abs(dx) < 1.0 else (1 if dx > 0 else -1)


def merge_plan(plan: Sequence[MovementSummary]) -> list[Move]:
    """A Plan's components as moves: consecutive same-way walks or climbs are one,
    rope grabs are marked (a jump the next move climbs from), and components
    with no planned start or end (the end-of-movement release) are dropped."""
    moves: list[Move] = []
    for index, component in enumerate(plan):
        if component.start is None or component.end is None:
            continue
        kind_type = component.movement_type
        if moves and moves[-1].type == kind_type and kind_type in _WALKS | _CLIMBS:
            last = moves[-1]
            moves[-1] = replace(
                last,
                end=component.end,
                length=last.length + component.length,
                components=(*last.components, index),
            )
            continue
        moves.append(
            Move(
                kind_type,
                component.start,
                component.end,
                component.length,
                component.duration,
                component.grabs_rope,
                (index,),
            )
        )
    for i, move in enumerate(moves[:-1]):
        if move.kind in ("jump", "drop") and moves[i + 1].type in _CLIMBS:
            moves[i] = replace(move, grabs_rope=True)
    return moves


@dataclass
class TrialData:
    """One Trial's measured phase: its cycles and reads, and its outcome."""

    batch: str
    trial: str
    cycles: list[CycleRecord] = field(default_factory=list)
    reads: list[Read] = field(default_factory=list)
    outcome: TrialOutcome | None = None

    @property
    def t0(self) -> float:
        return self.cycles[0].position.frame_time if self.cycles else 0.0


def split_trials(
    records: Iterable[Record],
) -> tuple[ScheduleHeader | None, list[TrialData]]:
    """The header and every Trial's measured cycles, reads and outcome."""
    header: ScheduleHeader | None = None
    trials: dict[tuple[str, str], TrialData] = {}
    for record in records:
        if isinstance(record, ScheduleHeader):
            header = record
            continue
        if isinstance(record, TrialOutcome):
            key = (record.batch, record.trial)
            trials.setdefault(key, TrialData(*key)).outcome = record
            continue
        if not isinstance(record, CycleRecord | SampleRecord):
            continue
        if record.phase != Phase.MEASURING:
            continue
        key = (record.batch, record.trial)
        entry = trials.setdefault(key, TrialData(*key))
        if isinstance(record, CycleRecord):
            entry.cycles.append(record)
        position = record.position
        if position.position is not None:
            entry.reads.append(
                Read(position.frame_time, *position.position, position.source)
            )
    for entry in trials.values():
        entry.reads = one_per_frame(entry.reads)
    return header, [t for t in trials.values() if t.cycles]


def walk_speed(header: ScheduleHeader | None) -> float:
    """Virtual px/s the plan walks at: `Physics.img`'s walkSpeed times the
    character's speed multiplier and the walk Calibration constant."""
    if header is None:
        return DEFAULT_WALK_SPEED
    base = (header.physics or {}).get("walkSpeed", DEFAULT_WALK_SPEED)
    return (
        base
        * (header.speed_multiplier or 1.0)
        * (header.calibration or {}).get("walk", 1.0)
    )


def walk_deceleration(header: ScheduleHeader | None) -> float:
    """Virtual px/s² a walk slides to rest at once its key is up: `Physics.img`'s
    walkDrag over the character's mass (`maple.model.mechanics.physics`);
    infinite (no slide) when the header carries no physics."""
    drag = None if header is None else (header.physics or {}).get("walkDrag")
    return math.inf if not drag else float(drag) / CHARACTER_MASS


def action_cap(trial: TrialData) -> float:
    """The Action duration cap the Trial's batch compiled against."""
    knobs = trial.outcome.knobs if trial.outcome is not None else None
    value = None if knobs is None else knobs.action_duration
    return DEFAULT_CUT if value is None else float(value)


# --- the Session ------------------------------------------------------------------

_EPOCH: Final = datetime(1970, 1, 1)
_LOG_TIME: Final = re.compile(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d+):::")
_COMPUTING: Final = re.compile(
    r"Computing path from \(([-\d.e]+), ([-\d.e]+)\) to \(([-\d.e]+), ([-\d.e]+)\)"
)


def _local_seconds(when: datetime) -> float:
    """
    Seconds on the Session's local wall clock (the timezone dropped).

    Every Session time is put on this one clock, and none depends on the zone
    of the machine running the report: an envelope timestamp is read in its own
    offset, the one the Session wrote it in; ``session.log``'s lines carry no
    offset and are already the Session's local time; a key record's epoch
    ``wall`` is converted with its own envelope's offset (`_key_event`).
    """
    return (when.replace(tzinfo=None) - _EPOCH).total_seconds()


@dataclass(frozen=True)
class KeyEvent:
    """
    One ``key.down`` or ``key.up`` record (#538). ``t`` is its payload's
    ``time.monotonic()``, which is the record's clock already: no offset.
    """

    t: float
    key: str
    down: bool
    origin: int | None = None
    cause: str | None = None
    #: A ``key.up`` for a key the Held-Keys Ledger did not hold.
    straggler: bool = False


@dataclass(frozen=True)
class Action:
    """One Action as the Session saw it, on the record's clock."""

    scheduled: float
    finished: float | None = None
    elapsed: float | None = None
    outcome: str | None = None
    #: Seconds from ``action.scheduled`` to the Action's first key record, both
    #: on the Session's wall clock; `None` when it recorded no key.
    to_first_key: float | None = None


@dataclass(frozen=True)
class Planning:
    """One Path computation from the Session's log, on the record's clock."""

    started: float
    ended: float | None
    origin: Point


@dataclass
class SessionTimes:
    """
    What the Session adds, put on the record's clock (frame capture time,
    `time.monotonic()`): ``offset`` is local wall clock minus record clock.
    """

    offset: float
    actions: dict[str, Action] = field(default_factory=dict)
    plannings: list[Planning] = field(default_factory=list)
    matched_reads: int = 0
    spread: float = 0.0
    #: The key records the offset was set from (their own ``wall`` and ``t``);
    #: 0 when it was set from matched reads (a Session from before #538).
    keyed_offset: int = 0
    #: With key records: how long after its frame's capture a ``position.read``
    #: event is written, median seconds (the read's own time). `None` without.
    read_time: float | None = None
    #: Each Action's key records, by Correlation ID, in time order. Empty for a
    #: Session from before #538.
    keys: dict[str, list[KeyEvent]] = field(default_factory=dict)


def load_session(session: Path, records: Sequence[Record]) -> SessionTimes | None:
    """
    The Session's Actions and Path computations, on the record's clock, or `None`
    when too few of its reads match the record's to set the clock.
    """
    telemetry = session / "telemetry.jsonl" if session.is_dir() else session
    directory = telemetry.parent
    reads: list[tuple[float, float, float]] = []
    scheduled: dict[str, float] = {}
    finished: dict[str, tuple[float, float | None, str | None]] = {}
    keys: dict[str, list[tuple[float, KeyEvent]]] = {}
    # The Session's zone, from the latest envelope that states one: what a key
    # record's epoch `wall` is read in. UTC only until the first one is seen.
    zone: tzinfo = UTC
    with telemetry.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            kind = event.get("event_type")
            if kind not in _SESSION_EVENTS:
                continue
            payload = event.get("payload") or {}
            cid = event.get("correlation_id")
            stamp = datetime.fromisoformat(event["timestamp"])
            if stamp.tzinfo is not None:
                zone = stamp.tzinfo
            if kind in ("key.down", "key.up"):
                if cid and payload.get("t") is not None:
                    keys.setdefault(cid, []).append(_key_event(kind, payload, zone))
                continue
            when = _local_seconds(stamp)
            if kind == "position.read":
                if payload.get("x") is not None and payload.get("y") is not None:
                    reads.append((when, float(payload["x"]), float(payload["y"])))
            elif kind == "action.scheduled" and cid:
                scheduled[cid] = when
            elif kind == "action.finished" and cid:
                ms = payload.get("elapsed_ms")
                finished[cid] = (
                    when,
                    None if ms is None else float(ms) / 1000.0,
                    payload.get("outcome"),
                )
    rows = [
        (r.position.frame_time, *r.position.position)
        for r in records
        if isinstance(r, CycleRecord | SampleRecord) and r.position.position is not None
    ]
    read_offset, matched, spread = _clock_offset(reads, rows)
    # A key record's own two clocks, where the Session has them: a read's event
    # is written after the read, so the reads' offset is late by its time.
    key_offsets = [
        w - k.t
        for events in keys.values()
        for w, k in events
        if not (math.isnan(w) or math.isnan(k.t))
    ]
    offset = statistics.median(key_offsets) if key_offsets else read_offset
    if offset is None:
        return None
    times = SessionTimes(
        offset,
        matched_reads=matched,
        spread=spread,
        keyed_offset=len(key_offsets),
        read_time=(
            read_offset - offset if key_offsets and read_offset is not None else None
        ),
    )
    for cid, events in keys.items():
        # By `t`, not by file order: records are written after the send.
        events.sort(key=lambda pair: pair[1].t)
        times.keys[cid] = [key for _, key in events]
    for cid, when in scheduled.items():
        done = finished.get(cid)
        walls = [w for w, _ in keys.get(cid, ()) if not math.isnan(w)]
        times.actions[cid] = Action(
            when - offset,
            None if done is None else done[0] - offset,
            None if done is None else done[1],
            None if done is None else done[2],
            min(walls) - when if walls else None,
        )
    log = directory / "session.log"
    if not log.exists():
        log = directory / "movement.log"
    if log.exists():
        times.plannings = _plannings(log, offset)
    return times


_SESSION_EVENTS: Final = frozenset(
    {"position.read", "action.scheduled", "action.finished", "key.down", "key.up"}
)


def _key_event(
    kind: str, payload: dict[str, object], zone: tzinfo
) -> tuple[float, KeyEvent]:
    """A key record as (its Session-local wall-clock seconds, the event on the
    record's clock). `zone` is the Session's, from its envelope: never the zone
    of the machine running the report."""
    origin = payload.get("origin")
    t = payload.get("t")
    wall = payload.get("wall")
    cause = payload.get("cause")
    return (
        _local_seconds(datetime.fromtimestamp(float(wall), tz=zone))
        if isinstance(wall, int | float)
        else math.nan,
        KeyEvent(
            float(t) if isinstance(t, int | float) else math.nan,
            str(payload.get("key")),
            kind == "key.down",
            origin if isinstance(origin, int) else None,
            None if cause is None else str(cause),
            kind == "key.up" and payload.get("held") is False,
        ),
    )


def _clock_offset(
    reads: Sequence[tuple[float, float, float]],
    rows: Sequence[tuple[float, float, float]],
) -> tuple[float | None, int, float]:
    """Local wall clock minus record clock: the median difference between each
    record read and the Session's read of the same position nearest in time."""
    if not reads or not rows:
        return None, 0, 0.0
    by_position: dict[tuple[float, float], list[float]] = {}
    for when, x, y in reads:
        by_position.setdefault((round(x, 1), round(y, 1)), []).append(when)
    first = min(rows)
    guesses = [
        when - first[0]
        for when in by_position.get((round(first[1], 1), round(first[2], 1)), [])
    ] or [reads[0][0] - first[0]]
    best: tuple[float | None, int, float] = (None, 0, 0.0)
    for guess in guesses[:5]:
        offset = guess
        diffs: list[float] = []
        for _ in range(3):
            diffs = []
            for t, x, y in rows:
                candidates = by_position.get((round(x, 1), round(y, 1)))
                if not candidates:
                    continue
                nearest = min(candidates, key=lambda w: abs(w - t - offset))
                if abs(nearest - t - offset) < 0.5:
                    diffs.append(nearest - t)
            if not diffs:
                break
            offset = statistics.median(diffs)
        if len(diffs) > best[1]:
            mid = statistics.median(diffs)
            spread = statistics.median(abs(d - mid) for d in diffs)
            best = (offset, len(diffs), spread)
    if best[1] < 5:
        return None, best[1], 0.0
    return best


def _plannings(log: Path, offset: float) -> list[Planning]:
    """Every ``Computing path`` line and the ``Movements`` or ``No path`` line
    that ends it, on the record's clock."""
    out: list[Planning] = []
    pending: tuple[float, Point] | None = None
    with log.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "movement_mechanics" not in line:
                continue
            stamp = _LOG_TIME.search(line)
            if stamp is None:
                continue
            when = (
                _local_seconds(datetime.strptime(stamp.group(1), "%Y-%m-%d %H:%M:%S"))
                + int(stamp.group(2)) / 1000.0
                - offset
            )
            computing = _COMPUTING.search(line)
            if computing is not None:
                if pending is not None:
                    out.append(Planning(pending[0], None, pending[1]))
                pending = (when, (float(computing.group(1)), float(computing.group(2))))
            elif pending is not None and (
                ":::Movements:" in line or ":::No path" in line
            ):
                out.append(Planning(pending[0], when, pending[1]))
                pending = None
    if pending is not None:
        out.append(Planning(pending[0], None, pending[1]))
    return out


# --- judging ----------------------------------------------------------------------


@dataclass
class Timing:
    """One cycle's loop timing, seconds; `None` where the Session has no line."""

    age_at_plan: float | None = None
    planning: float | None = None
    handoff: float | None = None
    age_at_schedule: float | None = None
    action: float | None = None
    ended: str | None = None
    gap: float | None = None
    wait: float | None = None
    no_plan: float | None = None
    in_flight: float | None = None
    read_and_plan: float | None = None
    stale: bool = False
    #: ``action.scheduled`` to the Action's first key record (#538).
    to_keys: float | None = None


@dataclass(frozen=True)
class KeyTiming:
    """
    A move judged at a key time (#538): where the character was when the key
    went (``x``, interpolated from the reads around ``t``), and how far that is
    from the plan along the travel direction (``px``, positive: late or long),
    also as time at the walk speed (``ms``; `None` for a vertical move).
    """

    t: float
    key: str
    x: float
    px: float
    ms: float | None


@dataclass
class Judged:
    """One measured cycle, judged."""

    trial: str
    cycle: int
    t: float
    position: Point
    kind: str
    move: Move | None
    key: Move | None
    lead: float = 0.0
    verdict: str = "no plan"
    takeoff: str = "n/a"
    takeoff_bracket: tuple[float, float] | None = None
    takeoff_times: tuple[float, float] | None = None
    landing: Point | None = None
    error: Point | None = None
    along: float | None = None
    duration: float = 0.0
    window: list[Read] = field(default_factory=list)
    timing: Timing | None = None
    dispatched_at: float | None = None
    finished_at: float | None = None
    cluster: int | None = None
    try_index: int | None = None
    tried: bool = False
    #: The take-off judged at the jump key's ``key.down``, when the Session has it.
    takeoff_key: KeyTiming | None = None
    #: A walk's stop judged at its key's ``key.up``, when the Session has it.
    stop_key: KeyTiming | None = None

    @property
    def missed(self) -> bool:
        return self.verdict.split(",")[0] in MISSES


def _departure(window: Sequence[Read], move: Move) -> int | None:
    sx, sy = move.start
    for j in range(1, len(window)):
        prev, cur = window[j - 1], window[j]
        if (
            abs(prev.y - sy) <= GROUND_Y
            and abs(prev.x - sx) <= ZONE_X
            and abs(cur.y - sy) > LIFT_Y
            and abs(cur.y - prev.y) > LIFT_Y
        ):
            return j
    return None


def _climbed(window: Sequence[Read], first_air: int) -> bool:
    """
    Whether the reads from the take-off on keep moving one way along one
    column for longer than any jump rises (``RISE_MAX``) and slower than a
    fall (``CLIMB_MAX``): the character climbed (up or down) instead of
    jumping off.
    """
    start = window[first_air - 1]
    way = 1 if window[first_air].y > start.y else -1
    last = start
    for read in window[first_air:]:
        if abs(read.x - start.x) > ROPE_X or (read.y - last.y) * way <= 0:
            break
        last = read
    span = last.t - start.t
    return span >= RISE_MAX and abs(last.y - start.y) / span <= CLIMB_MAX


def _landing(window: Sequence[Read], first_air: int, move: Move) -> Read:
    """
    Where the flight ended: the first read on the planned landing (within
    ``LAND_X``, or ``ROPE_X`` of a rope, and ``LAND_Y``) that the next read
    stays on (within ``SETTLE_DY`` in y; a rope's column), since the Plan's next move may walk or climb on from it at
    once; else the first of three reads within ``SETTLE_DY`` in y (two reads
    can straddle a jump's apex at one height; three cannot); else the last.
    """
    slack = ROPE_X if move.grabs_rope else LAND_X
    for m in range(first_air, len(window)):
        read = window[m]
        if abs(read.x - move.end[0]) <= slack and abs(read.y - move.end[1]) <= LAND_Y:
            if m + 1 == len(window):
                return read
            after = window[m + 1]
            if move.grabs_rope and abs(after.x - move.end[0]) <= ROPE_X:
                return read  # still on the rope's column: hanging or climbing
            if not move.grabs_rope and abs(after.y - read.y) <= SETTLE_DY:
                return read  # standing: not a pass through the apex
    for m in range(first_air, len(window) - 2):
        ys = [window[m].y, window[m + 1].y, window[m + 2].y]
        if max(ys) - min(ys) <= SETTLE_DY:
            return window[m]
    return window[-1]


def landing_verdict(move: Move, landing: Point) -> tuple[str, Point, float]:
    """The landing's verdict, its error vector and its error along the travel
    direction (positive: past the planned end)."""
    dx = landing[0] - move.end[0]
    dy = landing[1] - move.end[1]
    along = dx * move.direction if move.direction else dx
    if move.grabs_rope:
        if abs(dx) <= ROPE_X:
            return "ok", (dx, dy), along
    elif abs(dx) <= LAND_X and abs(dy) <= LAND_Y:
        return "ok", (dx, dy), along
    if abs(dy) <= LAND_Y or (move.grabs_rope and abs(dy) <= KEY_ROPE_Y):
        if move.direction == 0:
            return "off", (dx, dy), along
        return ("long" if along > 0 else "short"), (dx, dy), along
    if landing[1] > max(move.start[1], move.end[1]) + FALL_DROP:
        return "fell", (dx, dy), along
    if abs(landing[1] - move.start[1]) <= LAND_Y:
        # Back at the take-off's height: it never got up (or down) there.
        if move.direction and along > LAND_X:
            return "long", (dx, dy), along
        return "short", (dx, dy), along
    return "off", (dx, dy), along


def judge_cycle(
    judged: Judged, window: Sequence[Read], moves: Sequence[Move], reach: float
) -> None:
    """Fill in a cycle's judged move, verdict, take-off and landing."""
    judged.window = list(window)
    if not moves:
        return
    # A climb shorter than a landing's slack (a rope's last px before a jump
    # off it) is a lead, like a walk: the jump after it is the key move.
    index = next(
        (
            i
            for i, m in enumerate(moves)
            if m.kind != "walk" and not (m.kind == "climb" and m.length < LAND_Y)
        ),
        None,
    )
    judged.lead = sum(
        m.length for m in moves[: index if index is not None else 0] if m.kind == "walk"
    )
    if index is not None:
        key = moves[index]
        judged.key = key
        if key.kind in ("jump", "drop", "teleport"):
            j = _departure(window, key)
            if j is not None or judged.lead <= reach:
                judged.move, judged.kind = key, key.kind
                _judge_flight(judged, window, key, j)
                return
        elif key.kind == "climb":
            if index == 0 or judged.lead <= reach:
                judged.move, judged.kind = key, "climb"
                _judge_climb(judged, window, key, grab=index > 0)
                return
        elif key.kind == "portal" and judged.lead <= reach:
            judged.move, judged.kind = key, "portal"
            _judge_portal(judged, window, key)
            return
    walk = moves[0]
    judged.move, judged.kind = walk, walk.kind
    if walk.kind != "walk":
        judged.verdict = "en route"
        return
    if walk.length > reach:
        judged.verdict = "en route"
        return
    stop = window[-1]
    along = (stop.x - walk.end[0]) * (walk.direction or 1)
    judged.landing = (stop.x, stop.y)
    judged.error = (stop.x - walk.end[0], stop.y - walk.end[1])
    judged.along = along
    judged.verdict = (
        "ok" if abs(along) <= LAND_X else ("long" if along > 0 else "short")
    )


def _judge_flight(
    judged: Judged, window: Sequence[Read], key: Move, j: int | None
) -> None:
    if j is None:
        last = window[-1]
        ahead = (key.start[0] - last.x) * (key.direction or 1)
        judged.verdict = "not reached" if ahead > LAND_X else "no take-off"
        judged.landing = (last.x, last.y)
        return
    judged.tried = True
    ground, air = window[j - 1], window[j]
    judged.takeoff_times = (ground.t, air.t)
    if key.kind == "jump" and _climbed(window, j):
        judged.takeoff = "climbed"
        judged.verdict = "no take-off"
        last = window[-1]
        judged.landing = (last.x, last.y)
        return
    if not key.direction:
        offset = ground.x - key.start[0]
        judged.takeoff_bracket = (offset, air.x - key.start[0])
        judged.takeoff = "on spot" if abs(offset) <= LAND_X else "off spot"
    else:
        late = (ground.x - key.start[0]) * key.direction
        reach_air = (air.x - key.start[0]) * key.direction
        judged.takeoff_bracket = (late, reach_air)
        if reach_air < -TAKEOFF_SLACK:
            judged.takeoff = "early"
        elif late > TAKEOFF_SLACK:
            judged.takeoff = "late"
        else:
            judged.takeoff = "on time"
    landing = _landing(window, j, key)
    judged.landing = (landing.x, landing.y)
    verdict, error, along = landing_verdict(key, judged.landing)
    judged.error, judged.along = error, along
    if verdict != "ok" and judged.takeoff in ("early", "late", "off spot"):
        verdict = f"{verdict}, {judged.takeoff} take-off"
    judged.verdict = verdict


def _judge_climb(
    judged: Judged, window: Sequence[Read], key: Move, *, grab: bool
) -> None:
    ex, ey = key.end
    if any(abs(r.x - ex) <= ROPE_X and abs(r.y - ey) <= LAND_Y for r in window[1:]):
        judged.verdict = "ok"
    elif grab and not any(
        abs(r.x - key.start[0]) <= ROPE_X and abs(r.y - key.start[1]) > LIFT_Y
        for r in window
    ):
        judged.verdict = "no take-off"
    else:
        judged.verdict = "en route"
    if grab:
        judged.tried = True
    last = window[-1]
    judged.landing = (last.x, last.y)


def _judge_portal(judged: Judged, window: Sequence[Read], key: Move) -> None:
    judged.tried = True
    stepped = any(
        math.dist((a.x, a.y), (b.x, b.y)) >= PORTAL_STEP for a, b in pairwise(window)
    )
    near = any(math.dist((r.x, r.y), key.end) <= LAND_X for r in window)
    judged.verdict = "ok" if stepped or near else "no take-off"
    last = window[-1]
    judged.landing = (last.x, last.y)


def judge_trial(
    trial: TrialData,
    speed: float,
    session: SessionTimes | None,
    deceleration: float = math.inf,
) -> list[Judged]:
    """Every measured cycle of a Trial, judged, with its loop timing; judged
    again at the key times where the Session has them (`judge_keys`).
    `deceleration`: the walk's, virtual px/s² (``walkDrag`` over the mass)."""
    cap = action_cap(trial)
    reach = speed * cap
    out: list[Judged] = []
    cycles = trial.cycles
    end_t = trial.reads[-1].t if trial.reads else trial.t0
    for k, cycle in enumerate(cycles):
        position = cycle.position
        t = position.frame_time
        later = [
            c for c in cycles[k + 1 :] if c.plan and c.position.position is not None
        ]
        window_end = later[0].position.frame_time if later else end_t
        next_t = cycles[k + 1].position.frame_time if k + 1 < len(cycles) else end_t
        point = position.position or (math.nan, math.nan)
        judged = Judged(trial.trial, cycle.cycle, t, point, "no plan", None, None)
        judged.duration = max(0.0, next_t - t)
        if cycle.plan and position.position is not None:
            window = [r for r in trial.reads if t <= r.t <= window_end]
            if not window or window[0].t != t:
                window.insert(0, Read(t, *position.position, position.source))
            judge_cycle(judged, window, merge_plan(cycle.plan), reach)
            keys = (
                ()
                if session is None
                else session.keys.get(cycle.correlation_id or "", ())
            )
            if keys:
                judge_keys(judged, trial.reads, keys, speed, deceleration)
        elif position.position is None:
            judged.kind = "unsure"
            judged.verdict = "unsure read"
        out.append(judged)
    if session is not None:
        _timings(out, cycles, session, cap, [r.t for r in trial.reads])
    return out


#: The direction keys, by the names the input layer sends them under.
_DIRECTION_KEYS: Final = frozenset({"left", "right", "up", "down"})


def x_at(reads: Sequence[Read], t: float) -> tuple[float, float] | None:
    """
    The character's x at record-clock `t` and its speed along x then, px/s:
    linear between the two reads around `t`. `None` outside the reads.
    """
    times = [r.t for r in reads]
    i = bisect.bisect_left(times, t)
    if i < len(reads) and reads[i].t == t:
        before = reads[i - 1] if i > 0 else reads[i]
        after = reads[i + 1] if i + 1 < len(reads) else reads[i]
        span = after.t - before.t
        return reads[i].x, (after.x - before.x) / span if span > 0 else 0.0
    if i == 0 or i >= len(reads):
        return None
    before, after = reads[i - 1], reads[i]
    span = after.t - before.t
    if span <= 0:
        return None
    velocity = (after.x - before.x) / span
    return before.x + velocity * (t - before.t), velocity


def takeoff_key(keys: Sequence[KeyEvent], move: Move) -> KeyEvent | None:
    """
    The key that took `move` off: the Action's first ``key.down`` that is not a
    direction key. When the Action's records carry Provenance, it must come from
    one of the move's components, so a jump the Action never reached has none.
    "First" is by ``t``, never by file order: records are written after the send.
    """
    downs = [k for k in _by_time(keys) if k.down and k.key not in _DIRECTION_KEYS]
    if any(k.origin is not None for k in keys):
        downs = [k for k in downs if k.origin in move.components]
    return downs[0] if downs else None


def stop_key(keys: Sequence[KeyEvent], walk: Move) -> KeyEvent | None:
    """The ``key.up`` that ended `walk`: its direction key's first in the Action,
    by ``t``."""
    if not walk.direction:
        return None
    name = "right" if walk.direction > 0 else "left"
    return next((k for k in _by_time(keys) if not k.down and k.key == name), None)


def _by_time(keys: Sequence[KeyEvent]) -> list[KeyEvent]:
    """Key records in the order the keys went, by ``t``: the file's order is when
    each was written, which trails the send (`botting/telemetry_events.py`)."""
    return sorted(keys, key=lambda k: k.t)


def judge_keys(
    judged: Judged,
    reads: Sequence[Read],
    keys: Sequence[KeyEvent],
    speed: float,
    deceleration: float = math.inf,
) -> None:
    """
    Judge a cycle's move again at its key times (#538), where it has them.

    - A take-off (a jump or a drop that left the ground): the x at the jump
      key's ``key.down`` against the planned take-off x. Sideways: **early** more
      than ``TAKEOFF_SLACK`` short of it, **late** more than that past it, in px
      and in ms at the walk speed. Straight up or down: **on spot** within
      ``LAND_X``, else **off spot**. It replaces the bracket's take-off.
    - A walk judged on its stop: where the character comes to rest from its
      key's ``key.up`` (the x then, plus the slide from the speed it had,
      ``v² / 2 deceleration``) against the planned end: **ok** within
      ``LAND_X``, else **long** or **short**, in px and in ms at the walk speed.
      It replaces the verdict from the last read, which is added when the two
      disagree (``ok, stopped long``).
    """
    move = judged.move
    if move is None:
        return
    if (
        judged.kind in ("jump", "drop")
        and judged.takeoff_times is not None
        and judged.takeoff != "climbed"
    ):
        key = takeoff_key(keys, move)
        at = None if key is None else x_at(reads, key.t)
        if key is None or at is None:
            return
        x = at[0]
        if move.direction:
            px = (x - move.start[0]) * move.direction
            ms = px / speed * 1000.0 if speed > 0 else None
            takeoff = (
                "early"
                if px < -TAKEOFF_SLACK
                else ("late" if px > TAKEOFF_SLACK else "on time")
            )
        else:
            px = x - move.start[0]
            ms = None
            takeoff = "on spot" if abs(px) <= LAND_X else "off spot"
        judged.takeoff_key = KeyTiming(key.t, key.key, x, px, ms)
        judged.takeoff = takeoff
        base = judged.verdict.split(",")[0]
        judged.verdict = (
            f"{base}, {takeoff} take-off"
            if base != "ok" and takeoff in ("early", "late", "off spot")
            else base
        )
        return
    if judged.kind == "walk" and judged.verdict in ("ok", "long", "short"):
        key = stop_key(keys, move)
        at = None if key is None else x_at(reads, key.t)
        if key is None or at is None:
            return
        x, velocity = at
        moving = min(abs(velocity), speed) if velocity * move.direction > 0 else 0.0
        slide = 0.0 if math.isinf(deceleration) else moving**2 / (2 * deceleration)
        px = (x + slide * move.direction - move.end[0]) * move.direction
        judged.stop_key = KeyTiming(
            key.t, key.key, x, px, px / speed * 1000.0 if speed > 0 else None
        )
        by_key = "ok" if abs(px) <= LAND_X else ("long" if px > 0 else "short")
        judged.verdict = (
            by_key
            if by_key == judged.verdict
            else f"{by_key}, stopped {judged.verdict}"
        )


def _timings(
    out: list[Judged],
    cycles: Sequence[CycleRecord],
    session: SessionTimes,
    cap: float,
    read_times: Sequence[float],
) -> None:
    starts = [p.started for p in session.plannings]
    previous_finish: float | None = None
    for judged, cycle in zip(out, cycles, strict=True):
        action = session.actions.get(cycle.correlation_id or "")
        if action is None:
            continue
        timing = Timing()
        t = cycle.position.frame_time
        judged.dispatched_at = action.scheduled
        judged.finished_at = action.finished
        planning = _planning_for(session, starts, cycle)
        if planning is not None:
            timing.age_at_plan = planning.started - t
            if planning.ended is not None:
                timing.planning = planning.ended - planning.started
                timing.handoff = action.scheduled - planning.ended
                timing.read_and_plan = planning.ended - t
        timing.age_at_schedule = action.scheduled - t
        timing.to_keys = action.to_first_key
        timing.action = action.elapsed
        if action.elapsed is not None:
            if action.elapsed < cap - CUT_TOL:
                timing.ended = "plan end"
            elif action.elapsed > cap + CUT_TOL:
                timing.ended = "past cut"
            else:
                timing.ended = "cut"
        if previous_finish is not None:
            timing.gap = action.scheduled - previous_finish
            first = next(
                (
                    c.position.frame_time
                    for c in cycles
                    if c.position.frame_time >= previous_finish
                ),
                t,
            )
            first = min(first, t)
            timing.wait = (t if t < previous_finish else first) - previous_finish
            timing.stale = t < previous_finish
            timing.no_plan = max(0.0, t - first) if not timing.stale else 0.0
            # Samples captured after the finish and before the first cycle: the
            # loop still read as if the Action ran (the lock's release had not
            # reached it, or a sample's decide was under way).
            after = [r for r in read_times if previous_finish < r < first]
            timing.in_flight = (after[-1] - previous_finish) if after else 0.0
        judged.timing = timing
        if action.finished is not None:
            previous_finish = action.finished


def _planning_for(
    session: SessionTimes, starts: Sequence[float], cycle: CycleRecord
) -> Planning | None:
    if cycle.position.position is None:
        return None
    t = cycle.position.frame_time
    x, y = cycle.position.position
    i = bisect.bisect_left(starts, t - 0.05)
    for planning in session.plannings[i:]:
        if planning.started > t + 1.0:
            break
        if abs(planning.origin[0] - x) <= 0.06 and abs(planning.origin[1] - y) <= 0.06:
            return planning
    return None


def same_move(a: Move, b: Move) -> bool:
    """The same key move, seen from two cycles."""
    if a.kind != b.kind:
        return False
    dx = abs(a.end[0] - b.end[0])
    dy = abs(a.end[1] - b.end[1])
    limit_y = KEY_ROPE_Y if a.grabs_rope and b.grabs_rope else KEY_Y
    return dx <= KEY_X and dy <= limit_y


@dataclass
class Cluster:
    """Consecutive cycles that kept trying the same key move."""

    number: int
    trial: str
    move: Move
    cycles: list[Judged]
    tries: list[Judged]
    end_t: float

    @property
    def lost(self) -> float:
        """From the first try to the last try's start: what the repeats cost.
        The last try's own time is left out, so a cluster whose last try also
        missed lost more than this."""
        return self.tries[-1].t - self.tries[0].t


def find_clusters(judged: Sequence[Judged], start_number: int = 1) -> list[Cluster]:
    """Runs of cycles on the same key move with two tries or more."""
    clusters: list[Cluster] = []
    run: list[Judged] = []

    def close(end_t: float) -> None:
        key = run[0].key if run else None
        if key is None:
            return
        tries = [
            j for j in run if j.tried and j.move is not None and same_move(j.move, key)
        ]
        if len(tries) >= 2:
            clusters.append(
                Cluster(
                    start_number + len(clusters),
                    run[0].trial,
                    key,
                    list(run),
                    tries,
                    end_t,
                )
            )

    for item in judged:
        if item.key is None:
            if item.verdict in ("no plan", "unsure read"):
                continue
            close(item.t)
            run = []
            continue
        if run and run[0].key is not None and same_move(run[0].key, item.key):
            run.append(item)
            continue
        close(item.t)
        run = [item]
    close(judged[-1].t + judged[-1].duration if judged else 0.0)
    return clusters


def hypothesis(cluster: Cluster) -> str:
    """What the tries' landings say, in a sentence."""
    misses = [j for j in cluster.tries if j.missed]
    if not misses:
        return "every try landed: the repeats were replans, not misses"
    alongs = [j.along for j in misses if j.along is not None]
    takeoffs = Counter(j.takeoff for j in misses)
    verdicts = Counter(j.verdict.split(",")[0] for j in misses)
    parts: list[str] = []
    if verdicts.get("fell", 0) * 2 > len(misses):
        parts.append(
            "most tries fell: the take-off is past the edge, or the reach is short"
        )
    if alongs and all(a > LAND_X for a in alongs):
        parts.append(f"past the landing every time ({_range(alongs)} px along)")
    elif alongs and all(a < -LAND_X for a in alongs):
        parts.append(f"short of the landing every time ({_range(alongs)} px along)")
    elif alongs:
        parts.append(f"no consistent side ({_range(alongs)} px along)")
    if len(alongs) >= 3:
        mags = [abs(a) for a in alongs]
        if all(b > a for a, b in pairwise(mags)):
            parts.append("the miss grows try after try")
    if takeoffs.get("early", 0) * 2 > len(misses):
        parts.append("take-offs early (left the ground before the planned x)")
    elif takeoffs.get("late", 0) * 2 > len(misses):
        parts.append("take-offs late (still on the ground past the planned x)")
    elif takeoffs.get("on time", 0) == len(misses):
        parts.append("take-offs on time, so the flight itself carries it off")
    if cluster.move.grabs_rope and alongs and all(a > LAND_X for a in alongs):
        parts.append(
            "a rope grab overshot: the jump passes the rope without catching it"
        )
    return "; ".join(parts) or "not enough reads to say"


# --- numbers ----------------------------------------------------------------------


def _pct(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def stats(values: Iterable[float | None]) -> str:
    """``n, median, p90, max`` of a list, or ``n 0``."""
    clean = [v for v in values if v is not None and not math.isnan(v)]
    if not clean:
        return "n 0"
    return (
        f"n {len(clean)}, median {statistics.median(clean):.2f}, "
        f"p90 {_pct(clean, 0.9):.2f}, max {max(clean):.2f}"
    )


def _ms(values: Iterable[float | None]) -> str:
    clean = [v * 1000 for v in values if v is not None]
    if not clean:
        return "-"
    return f"{statistics.median(clean):.0f} / {_pct(clean, 0.9):.0f} / {max(clean):.0f} (n {len(clean)})"


def _range(values: Sequence[float]) -> str:
    return ", ".join(f"{v:+.0f}" for v in values)


def _xy(point: Point | None) -> str:
    if point is None or math.isnan(point[0]):
        return "-"
    return f"({point[0]:.0f}, {point[1]:.0f})"


@dataclass
class Summary:
    """One Trial's totals: what the comparison sets side by side."""

    label: str
    trial: str
    start: tuple[int, int] | None
    target: tuple[int, int] | None
    result: str
    duration: float
    cycles: int
    by_kind: dict[str, float]
    lost: float
    clusters: int
    walk_errors: list[float]
    jump_errors: list[float]
    jump_ok: tuple[int, int]
    verdicts: Counter[str]
    gaps: list[float]
    handoffs: list[float]
    ages: list[float]
    actions: list[float]
    cuts: tuple[int, int]
    #: Take-offs judged at the jump key: px from the planned take-off (+ late).
    takeoff_key_px: list[float] = field(default_factory=list[float])
    #: Walk stops judged at the key: px from the planned end (+ long).
    stop_key_px: list[float] = field(default_factory=list[float])
    #: Schedule to first key, seconds.
    to_keys: list[float] = field(default_factory=list[float])


def summarize(
    label: str, trial: TrialData, judged: Sequence[Judged], clusters: Sequence[Cluster]
) -> Summary:
    by_kind: dict[str, float] = {}
    for j in judged:
        by_kind[j.kind] = by_kind.get(j.kind, 0.0) + j.duration
    walks = [j.along for j in judged if j.kind == "walk" and j.along is not None]
    flights = [j for j in judged if j.kind in ("jump", "drop") and j.tried]
    timings = [j.timing for j in judged if j.timing is not None]
    outcome = trial.outcome
    return Summary(
        label,
        trial.trial,
        None if outcome is None else outcome.start,
        None if outcome is None else outcome.target,
        "-" if outcome is None else outcome.result,
        sum(j.duration for j in judged) if outcome is None else outcome.duration,
        len(judged),
        by_kind,
        sum(c.lost for c in clusters),
        len(clusters),
        walks,
        [math.hypot(*j.error) for j in flights if j.error is not None],
        (sum(1 for j in flights if not j.missed), len(flights)),
        Counter(j.verdict.split(",")[0] for j in judged),
        [t.gap for t in timings if t.gap is not None],
        [t.handoff for t in timings if t.handoff is not None],
        [t.age_at_schedule for t in timings if t.age_at_schedule is not None],
        [t.action for t in timings if t.action is not None],
        (
            sum(1 for t in timings if t.ended in ("cut", "past cut")),
            sum(1 for t in timings if t.ended),
        ),
        [j.takeoff_key.px for j in judged if j.takeoff_key is not None],
        [j.stop_key.px for j in judged if j.stop_key is not None],
        [t.to_keys for t in timings if t.to_keys is not None],
    )


# --- analysis of one run ----------------------------------------------------------


@dataclass
class Run:
    """One record (and its Session), judged."""

    label: str
    header: ScheduleHeader | None
    trials: list[TrialData]
    judged: dict[str, list[Judged]]
    clusters: list[Cluster]
    session: SessionTimes | None
    summaries: list[Summary]
    cycles: list[CycleRecord]
    speed: float


def analyze(record: Path, session_dir: Path | None, label: str | None = None) -> Run:
    records = read_records(record)
    header, trials = split_trials(records)
    session = load_session(session_dir, records) if session_dir is not None else None
    speed = walk_speed(header)
    deceleration = walk_deceleration(header)
    judged: dict[str, list[Judged]] = {}
    clusters: list[Cluster] = []
    summaries: list[Summary] = []
    name = label or record.stem
    for trial in trials:
        items = judge_trial(trial, speed, session, deceleration)
        found = find_clusters(items, start_number=len(clusters) + 1)
        for cluster in found:
            for i, item in enumerate(cluster.tries, start=1):
                item.cluster, item.try_index = cluster.number, i
        clusters.extend(found)
        judged[trial.trial] = items
        summaries.append(summarize(name, trial, items, found))
    cycles = [c for t in trials for c in t.cycles]
    return Run(
        name, header, trials, judged, clusters, session, summaries, cycles, speed
    )


# --- the report -------------------------------------------------------------------


def render(
    run: Run, others: Sequence[Run], moments: Sequence[str], plot: Path | None
) -> str:
    lines: list[str] = []
    header = run.header
    title = header.schedule if header is not None else run.label
    lines.append(f"# Trial report: {title}")
    lines.append("")
    if header is not None:
        lines.append(
            f"Map {header.map} ({header.map_id}); started {header.started_at}; "
            f"walk speed planned {run.speed:.0f} px/s."
        )
    if run.session is None:
        lines.append(
            "No Session given (or its reads did not match the record's): no key "
            "times and no loop timing."
        )
    else:
        session = run.session
        if session.keyed_offset:
            read_time = (
                ""
                if session.read_time is None
                else (
                    f"; a `position.read` is written a median "
                    f"{session.read_time * 1000:.0f} ms after its frame's capture "
                    f"(the read's own time)"
                )
            )
            lines.append(
                f"Session clock set from {session.keyed_offset} key records' own "
                f"wall and monotonic times{read_time}."
            )
        else:
            lines.append(
                f"Session clock matched on {session.matched_reads} reads "
                f"(median deviation {session.spread * 1000:.1f} ms; late by the "
                f"read's own time, which a Session without key records cannot "
                f"give)."
            )
        keyed = sum(
            1 for a in run.session.actions.values() if a.to_first_key is not None
        )
        if run.session.keys:
            lines.append(
                f"Key times: {keyed} of {len(run.session.actions)} Actions recorded "
                f"their keys (`key.down`/`key.up`), on the record's clock: take-offs "
                f"and walk stops are judged at the key where the Action has one."
            )
        else:
            lines.append(
                "Key times: none in this Session (it predates `key.down`/`key.up`, "
                "#538): take-offs and stops are judged from the reads alone."
            )
    if plot is not None:
        lines.append(f"\n![route]({plot.name})")
    lines.append("")
    lines.append(
        "Positions are virtual px (y grows downward). Times are seconds from the "
        "Trial's first measured read. The verdicts and their limit are in "
        "`toolkit/trial_report.py`'s docstring; sample spacing bounds every one."
    )
    for trial in run.trials:
        lines.extend(_render_trial(run, trial))
    lines.extend(_render_clusters(run))
    lines.extend(_render_totals(run))
    if run.session is not None:
        lines.extend(_render_timing(run))
    lines.extend(_render_where(run))
    if others:
        lines.extend(_render_comparison([run, *others]))
    for moment in moments:
        lines.extend(_render_moment(run, moment))
    lines.extend(_render_record_note())
    return "\n".join(lines) + "\n"


def _render_trial(run: Run, trial: TrialData) -> list[str]:
    items = run.judged[trial.trial]
    t0 = trial.t0
    outcome = trial.outcome
    out = ["", f"## Trial {trial.trial}", ""]
    if outcome is not None:
        out.append(
            f"{_xy(outcome.start)} to {_xy(outcome.target)}: **{outcome.result}** in "
            f"{outcome.duration:.1f} s, {outcome.cycles} cycles."
        )
        out.append("")
    out.append(
        "| cyc | t | at | move | planned start -> end | lead | dispatch / finish | "
        "take-off | landing / stop | error (dx, dy) | verdict |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for j in items:
        if j.move is None:
            out.append(
                f"| {j.cycle} | {j.t - t0:.1f} | {_xy(j.position)} | - | - | - | "
                f"{_dispatch(j, t0)} | - | - | - | {j.verdict} |"
            )
            continue
        move = j.move
        takeoff = j.takeoff
        details: list[str] = []
        if j.takeoff_key is not None:
            details.append(
                f"key {_key_offset(j.takeoff_key)} at {j.takeoff_key.t - t0:.2f} s"
            )
        if j.takeoff_bracket is not None:
            bracket = (
                f"reads {j.takeoff_bracket[0]:+.0f}..{j.takeoff_bracket[1]:+.0f} px"
            )
            if j.takeoff_times is not None:
                bracket += (
                    f", {j.takeoff_times[0] - t0:.2f}..{j.takeoff_times[1] - t0:.2f} s"
                )
            details.append(bracket)
        if details:
            takeoff += f" ({'; '.join(details)})"
        stop = _xy(j.landing)
        if j.stop_key is not None:
            stop += (
                f" (key up at x {j.stop_key.x:.0f}, {j.stop_key.t - t0:.2f} s: "
                f"{_key_offset(j.stop_key)})"
            )
        verdict = j.verdict
        if j.cluster is not None:
            verdict += f", retried (C{j.cluster} try {j.try_index})"
        error = "-" if j.error is None else f"({j.error[0]:+.0f}, {j.error[1]:+.0f})"
        out.append(
            f"| {j.cycle} | {j.t - t0:.1f} | {_xy(j.position)} | {move.type} "
            f"{move.length:.0f} | {_xy(move.start)} -> {_xy(move.end)} | {j.lead:.0f} | "
            f"{_dispatch(j, t0)} | {takeoff} | {stop} | {error} | {verdict} |"
        )
    misses = [j for j in items if j.missed]
    if misses:
        out.append("")
        out.append("Reads around each miss (t s: x, y):")
        out.append("")
        for j in misses:
            reads = "; ".join(
                f"{r.t - t0:.2f}: {r.x:.0f}, {r.y:.0f}" for r in j.window[:12]
            )
            out.append(f"- cycle {j.cycle} ({j.verdict}): {reads}")
    return out


def _key_offset(timing: KeyTiming) -> str:
    """A key timing's offset from the plan, px and (sideways) ms."""
    text = f"{timing.px:+.0f} px"
    if timing.ms is not None:
        text += f", {timing.ms:+.0f} ms"
    return text


def _dispatch(j: Judged, t0: float) -> str:
    if j.dispatched_at is None:
        return "-"
    finished = "-" if j.finished_at is None else f"{j.finished_at - t0:.2f}"
    return f"{j.dispatched_at - t0:.2f} / {finished}"


def _render_clusters(run: Run) -> list[str]:
    out = [
        "",
        "## Clusters of retries",
        "",
        (
            "Seconds lost run from the first try to the last try's start: the last "
            "try's own time is left out, so when it missed too, the loss is larger."
        ),
        "",
    ]
    if not run.clusters:
        out.append("None: no key move was tried twice in a row.")
        return out
    for c in run.clusters:
        trial = next(t for t in run.trials if t.trial == c.trial)
        t0 = trial.t0
        move = c.move
        offsets = "; ".join(
            f"try {j.try_index} at {j.t - t0:.1f} s: {j.verdict}, "
            f"error {('-' if j.error is None else f'({j.error[0]:+.0f}, {j.error[1]:+.0f})')}"
            f", along {('-' if j.along is None else f'{j.along:+.0f}')}, take-off {j.takeoff}"
            for j in c.tries
        )
        out.append(
            f"- **C{c.number}** ({c.trial}) {move.type} {_xy(move.start)} -> {_xy(move.end)}"
            f"{' (rope grab)' if move.grabs_rope else ''}: {len(c.tries)} tries over "
            f"{len(c.cycles)} cycles from {c.tries[0].t - t0:.1f} s, "
            f"last try {c.tries[-1].verdict}, "
            f"**{c.lost:.1f} s lost**."
        )
        out.append(f"  - {offsets}")
        variants = Counter(
            f"{j.move.type} {_xy(j.move.start)} -> {_xy(j.move.end)}"
            for j in c.tries
            if j.move is not None
        )
        if len(variants) > 1:
            out.append(
                "  - Planned as: "
                + "; ".join(f"{v} (x{n})" for v, n in variants.most_common())
            )
        elsewhere = [
            j
            for j in run.judged[c.trial]
            if j.tried
            and j.move is not None
            and same_move(j.move, c.move)
            and j not in c.cycles
        ]
        if elsewhere:
            out.append(
                "  - The same move was also tried outside this run of cycles: "
                + "; ".join(
                    f"cycle {j.cycle} at {j.t - t0:.1f} s ({j.verdict})"
                    for j in elsewhere
                )
            )
        out.append(f"  - Hypothesis: {hypothesis(c)}.")
    return out


def _render_totals(run: Run) -> list[str]:
    out = ["", "## Totals", ""]
    for s in run.summaries:
        kinds = ", ".join(
            f"{k} {v:.1f} s"
            for k, v in sorted(s.by_kind.items(), key=lambda kv: -kv[1])
        )
        verdicts = ", ".join(f"{k} {v}" for k, v in s.verdicts.most_common())
        out.append(
            f"**{s.trial}**: {s.result} in {s.duration:.1f} s, {s.cycles} cycles."
        )
        out.append("")
        out.append(f"- Time by move kind (cycle to next cycle): {kinds}.")
        out.append(
            f"- Time lost to retries: {s.lost:.1f} s over {s.clusters} cluster(s)."
        )
        out.append(
            f"- Walk stop error along the walk, px (+ past the end): {stats(s.walk_errors)}."
        )
        out.append(
            f"- Jump and drop landing error, px: {stats(s.jump_errors)}; ok {s.jump_ok[0]} of {s.jump_ok[1]}."
        )
        if s.takeoff_key_px or s.stop_key_px:
            out.append(
                f"- At the key: take-off px from the planned take-off (+ late) "
                f"{stats(s.takeoff_key_px)}; walk stop px from the planned end "
                f"(+ long) {stats(s.stop_key_px)}."
            )
        out.append(f"- Verdicts: {verdicts}.")
        out.append("")
    return out


def _render_timing(run: Run) -> list[str]:
    out = ["", "## Loop timing", ""]
    keyed = run.session is not None and bool(run.session.keys)
    out.append(
        "Per dispatched cycle, ms as median / p90 / max (n). "
        + (
            "Schedule to first key: `action.scheduled` to the Action's first "
            "`key.down` or `key.up`, both on Main Process's wall clock (the focus "
            "lock, the compile and the first `SendInput`)."
            if keyed
            else "Schedule to first key is not in this Session (no `key.down` "
            "records, #538)."
        )
    )
    out.append("")
    all_judged = [
        j for items in run.judged.values() for j in items if j.timing is not None
    ]
    groups: dict[str, list[Judged]] = {"all": all_judged}
    for j in all_judged:
        groups.setdefault(j.kind, []).append(j)
    out.append(
        "| moves | read age at planning | planning | hand-off | read age at schedule | "
        "schedule -> first key | Action | gap finish -> next schedule | of which loop "
        "wait | (samples after finish) | no-Plan cycles | read + planning |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, items in groups.items():
        timings = [j.timing for j in items if j.timing is not None]
        out.append(
            f"| {name} | {_ms(t.age_at_plan for t in timings)} | "
            f"{_ms(t.planning for t in timings)} | {_ms(t.handoff for t in timings)} | "
            f"{_ms(t.age_at_schedule for t in timings)} | {_ms(t.to_keys for t in timings)} | "
            f"{_ms(t.action for t in timings)} | "
            f"{_ms(t.gap for t in timings)} | {_ms(t.wait for t in timings)} | "
            f"{_ms(t.in_flight for t in timings)} | {_ms(t.no_plan for t in timings)} | {_ms(t.read_and_plan for t in timings)} |"
        )
    timings = [j.timing for j in all_judged if j.timing is not None]
    ended = Counter(t.ended for t in timings if t.ended)
    stale = sum(1 for t in timings if t.stale)
    out.append("")
    out.append(
        "Why Actions ended: "
        + (", ".join(f"{k} {v}" for k, v in ended.most_common()) or "-")
        + f". Cycles planned on a frame captured before the previous Action "
        f"finished (stale frame): {stale} of {sum(1 for t in timings if t.gap is not None)}."
    )
    total_gap = sum(t.gap for t in timings if t.gap is not None)
    total = sum(s.duration for s in run.summaries)
    if total > 0:
        out.append(
            f"Time between Actions (no Action running, keys left as the last one "
            f"left them): {total_gap:.1f} s of {total:.1f} s ({100 * total_gap / total:.0f}%)."
        )
    out.append("")
    out.append(
        "**Against the outcome of the move that followed** (jumps, drops and in-reach walks with a verdict):"
    )
    out.append("")
    judgedmoves = [
        j
        for j in all_judged
        if j.timing is not None
        and j.verdict not in ("en route", "no plan", "unsure read")
        and j.kind in ("jump", "drop", "walk", "climb", "portal")
    ]
    for label, value in (
        ("gap before it", lambda t: t.gap),
        ("read age at schedule", lambda t: t.age_at_schedule),
        ("loop wait", lambda t: t.wait),
    ):
        ok = [
            value(j.timing)
            for j in judgedmoves
            if not j.missed and value(j.timing) is not None
        ]
        miss = [
            value(j.timing)
            for j in judgedmoves
            if j.missed and value(j.timing) is not None
        ]
        note = " (too small to say)" if min(len(ok), len(miss)) < SMALL else ""
        out.append(f"- {label}: ok moves {_ms(ok)}, missed moves {_ms(miss)}{note}.")
        both = ok + miss
        if both:
            cut = statistics.median(both)
            long_miss = sum(
                1
                for j in judgedmoves
                if value(j.timing) is not None and value(j.timing) > cut and j.missed
            )
            long_n = sum(
                1
                for j in judgedmoves
                if value(j.timing) is not None and value(j.timing) > cut
            )
            short_miss = sum(
                1
                for j in judgedmoves
                if value(j.timing) is not None and value(j.timing) <= cut and j.missed
            )
            short_n = sum(
                1
                for j in judgedmoves
                if value(j.timing) is not None and value(j.timing) <= cut
            )
            out.append(
                f"  - above its median ({cut * 1000:.0f} ms): {long_miss} missed of {long_n}; "
                f"at or below: {short_miss} missed of {short_n}."
            )
    return out


def _render_where(run: Run) -> list[str]:
    timings = [
        j.timing for items in run.judged.values() for j in items if j.timing is not None
    ]
    gap = [t.gap for t in timings if t.gap is not None]
    wait = [t.wait for t in timings if t.wait is not None]
    handoff = [t.handoff for t in timings if t.handoff is not None]
    ended = Counter(t.ended for t in timings if t.ended)

    def med(values: Sequence[float]) -> float:
        return statistics.median(values) * 1000 if values else math.nan

    out = ["", "## Where the time goes, and the options (none changed here)", ""]
    out.append(
        "The settings, from the code. Measured medians are this run's; `-` "
        "without a Session."
    )
    out.append("")
    out.append(
        f"- **The {DEFAULT_CUT:g} s cut**: `TrialRunner.DEFAULT_ACTION_DURATION = {DEFAULT_CUT}` "
        f"(`maple/decision_makers/trial_runner.py`), handed to `compile_movements` "
        f"as `total_duration` (`data.action_duration`, "
        f"`maple/decision_makers/mixins/_rotation_mixins.py`). **Pure configuration**: "
        f"the `action_duration` Knob of a schedule batch (`configs/trials/*.json`, "
        f"unset in the Ellinia schedules, so {DEFAULT_CUT}). Actions here: "
        f"{', '.join(f'{k} {v}' for k, v in ended.most_common()) or '-'}."
    )
    out.append(
        f"- **The decision loop's period**: `TrialRunner._throttle = {LOOP_PERIOD}` "
        f"(`DecisionMaker._decision_loop`, `botting/core/decision_maker.py`, #508). "
        f"**Pure configuration**: the `decision_interval` Knob. The loop wait "
        f"(finish to next capture) median: {med(wait):.0f} ms."
    )
    out.append(
        f"- **Main Process's hand-off throttle**: `AsyncTaskManager._throttle = {HANDOFF_THROTTLE}` "
        f"(`botting/core/async_task_manager.py`), a sleep before every queue read: "
        f"a request waits only when it comes within {HANDOFF_THROTTLE} s of the previous one. "
        f"Code, not configuration. Hand-off median: {med(handoff):.0f} ms."
    )
    out.append(
        f"- **The frame cache**: `current_frame` is re-grabbed only when older than "
        f"{FRAME_CACHE} s (`ClientProvider.FRAME_REFRESH`), so a cycle can plan on a sample's frame "
        "from before the Action finished (the stale-frame count above)."
    )
    out.append(
        "- **The Continuation across the cut** (#519, `movement_mechanics_v2`): a cut "
        "leaves the direction key down, and `_finish_instead_of_cut` (#503) and "
        "`_jump_to_finish` (#515) already compile past the cap when the cut would "
        "land too near a stop or an edge take-off."
    )
    out.append("")
    out.append(
        f"The options, ranked by the seconds each would save over this run's "
        f"gaps between Actions (median {med(gap):.0f} ms), every other interval "
        f"kept as measured. All of them change when keys reach the game "
        f"(C-KEYS): each needs a Trial at the client before and after, and this "
        f"report run on both."
    )
    out.append("")
    for rank, (_, text) in enumerate(rank_options(timings), start=1):
        out.append(f"{rank}. {text}")
    return out


def rank_options(timings: Sequence[Timing]) -> list[tuple[float, str]]:
    """
    The options for the cut and the throttle, each with the seconds it would
    save over the run on these timings (negative: it would cost), best first.

    Rough by design: each estimate keeps every other interval as measured, and
    none says what the change does to the moves' accuracy, which only a Trial
    at the client can.
    """
    gaps = [t for t in timings if t.gap is not None]
    n = len(gaps)
    waits = [t.wait for t in gaps if t.wait is not None]
    reads = [t.read_and_plan for t in gaps if t.read_and_plan is not None]
    handoffs = [t.handoff for t in timings if t.handoff is not None]
    cuts = sum(1 for t in timings if t.ended in ("cut", "past cut"))
    stale = sum(1 for t in timings if t.stale)
    med_gap = statistics.median([t.gap for t in gaps if t.gap is not None] or [0.0])
    med_read = statistics.median(
        [t.read_and_plan for t in timings if t.read_and_plan is not None] or [0.0]
    )
    options: list[tuple[float, str]] = []
    saving = sum(reads)
    options.append(
        (
            saving,
            (
                f"**Plan the next piece before the current one ends** (a pipelined "
                f"Continuation: read and plan during the Action's last read interval, "
                f"schedule at the finish). Would save about {saving:.1f} s here (the "
                f"read and the planning, {n} boundaries). Risk: the plan starts from "
                f"where the character is predicted to be at the cut, not where it was "
                f"read, which no record shows for a plan yet; it touches "
                f"compile-at-dispatch (ADR 0002) and the one-Action lock. Code and a "
                f"spec, not configuration."
            ),
        )
    )
    saving = sum(max(0.0, w) for w in waits)
    options.append(
        (
            saving,
            (
                f"**Done (#540): release the loop at once when an Action finishes.** "
                f"A cycle whose sample read would outlast the Action's due end (its "
                f"dispatch plus the cap) waits on the lock instead, and decides when "
                f"it is released (`TrialRunner._finish_near`). The loop wait left "
                f"here: {saving:.1f} s over {n} boundaries, near none after a cut in "
                f"a Session from after #540; the Action's last sample is its cost."
            ),
        )
    )
    saving = n * LOOP_PERIOD / 4
    options.append(
        (
            saving,
            (
                f"**A shorter `decision_interval`** ({LOOP_PERIOD} s to {LOOP_PERIOD / 2:g} s; a schedule Knob, pure "
                f"configuration). At most half the period cut off each boundary's wait, "
                f"about {saving:.1f} s here; costs twice the sample reads (CPU), and does "
                f"nothing for the part of the wait that is a read."
            ),
        )
    )
    saving = cuts / 3 * med_gap
    options.append(
        (
            saving,
            (
                f"**A longer cut** (`action_duration` {DEFAULT_CUT} to {DEFAULT_CUT * 1.5:g} s; a schedule Knob, pure "
                f"configuration). A third fewer boundaries on the {cuts} Actions that ended "
                f"on the cut, about {saving:.1f} s; but each piece runs longer on one read, "
                f"so a walk's stop and a take-off rest more on the compiled timing (#503, "
                f"#515). Try it in one batch and compare with this report."
            ),
        )
    )
    saving = sum(handoffs)
    options.append(
        (
            saving,
            (
                f"**Lower `AsyncTaskManager._throttle`** ({HANDOFF_THROTTLE} s). Hand-off is only "
                f"{saving:.1f} s in all here: the queue is idle when a request comes, so "
                f"the sleep is already over. Generic engine code; nothing to gain."
            ),
        )
    )
    saving = -n * med_read if stale == 0 else stale * med_gap - n * med_read
    options.append(
        (
            saving,
            (
                f"**Force a fresh frame for each decision** (the {FRAME_CACHE} s frame cache). "
                f"{stale} cycle(s) planned on a frame from before the finish; it adds a "
                f"read to every boundary, about {-saving:.1f} s here if nothing else changes."
                if saving < 0
                else f"**Force a fresh frame for each decision**: {stale} stale-frame cycles."
            ),
        )
    )
    saving = -cuts * med_gap
    options.append(
        (
            saving,
            (
                f"**A shorter cut** (`action_duration` 0.5 s). Twice the boundaries: about "
                f"{-saving:.1f} s more here unless the gap shrinks first; more fresh plans."
            ),
        )
    )
    options.sort(key=lambda option: -option[0])
    return options


def _render_comparison(runs: Sequence[Run]) -> list[str]:
    out = ["", "## Side by side", ""]
    base = runs[0]
    for summary in base.summaries:
        rows: list[Summary] = [summary]
        for other in runs[1:]:
            match = next(
                (
                    s
                    for s in other.summaries
                    if s.start == summary.start and s.target == summary.target
                ),
                next((s for s in other.summaries if s.trial == summary.trial), None),
            )
            if match is not None:
                rows.append(match)
        if len(rows) < 2:
            continue
        out.append(f"**{_xy(summary.start)} to {_xy(summary.target)}**")
        out.append("")
        out.append("| | " + " | ".join(f"{s.label}: {s.trial}" for s in rows) + " |")
        out.append("|---|" + "---|" * len(rows))

        def row(name: str, cells: Iterable[str]) -> None:
            out.append(f"| {name} | " + " | ".join(cells) + " |")

        row(
            "result",
            (f"{s.result}, {s.duration:.1f} s, {s.cycles} cycles" for s in rows),
        )
        kinds = sorted({k for s in rows for k in s.by_kind})
        for kind in kinds:
            row(f"time in {kind}", (f"{s.by_kind.get(kind, 0.0):.1f} s" for s in rows))
        row(
            "lost to retries", (f"{s.lost:.1f} s ({s.clusters} clusters)" for s in rows)
        )
        row("walk stop error px", (stats(s.walk_errors) for s in rows))
        row(
            "jump landing error px",
            (f"{stats(s.jump_errors)}; ok {s.jump_ok[0]}/{s.jump_ok[1]}" for s in rows),
        )
        row("gap between Actions ms", (_ms(s.gaps) for s in rows))
        row("hand-off ms", (_ms(s.handoffs) for s in rows))
        row("read age at schedule ms", (_ms(s.ages) for s in rows))
        row("Action ms", (_ms(s.actions) for s in rows))
        row("schedule -> first key ms", (_ms(s.to_keys) for s in rows))
        row("take-off at key px (+ late)", (stats(s.takeoff_key_px) for s in rows))
        row("walk stop at key px (+ long)", (stats(s.stop_key_px) for s in rows))
        row("ended on the cut", (f"{s.cuts[0]} of {s.cuts[1]}" for s in rows))
        out.append("")
    if len(out) == 3:
        out.append(
            "No Trial of the other records goes from the same start to the same target."
        )
    return out


def _render_moment(run: Run, moment: str) -> list[str]:
    out = ["", f"## Moment {moment}", ""]
    located = locate_moment(run, moment)
    if located is None:
        out.append(
            "Could not place it: give `trial@seconds`, or `HH:MM:SS` with the "
            "Session (local time) or as the record's UTC wall clock."
        )
        return out
    trial, t = located
    items = run.judged[trial.trial]
    near = [j for j in items if j.t - 3.0 <= t <= j.t + j.duration + 3.0]
    out.append(f"{trial.trial} at {t - trial.t0:.1f} s. Moves within 3 s:")
    out.append("")
    for j in near:
        move = (
            "-"
            if j.move is None
            else f"{j.move.type} {_xy(j.move.start)} -> {_xy(j.move.end)}"
        )
        flag = " **flagged**" if j.missed or j.cluster is not None else ""
        out.append(
            f"- cycle {j.cycle} at {j.t - trial.t0:.1f} s ({j.duration:.1f} s): {move}: "
            f"{j.verdict}{flag}"
        )
    if not any(j.missed or j.cluster is not None for j in near):
        out.append("")
        out.append(
            "Nothing flagged there. What is missing: no read showed a miss; the "
            "sample spacing or the thresholds above may hide it, or what was seen "
            "is not a position (a key, an animation)."
        )
    return out


def locate_moment(run: Run, moment: str) -> tuple[TrialData, float] | None:
    """A moment as (Trial, record-clock time)."""
    if "@" in moment:
        name, seconds = moment.rsplit("@", 1)
        trial = next((t for t in run.trials if t.trial == name), None)
        if trial is None:
            return None
        return trial, trial.t0 + float(seconds)
    try:
        clock = datetime.strptime(moment, "%H:%M:%S")
    except ValueError:
        return None
    second_of_day = clock.hour * 3600 + clock.minute * 60 + clock.second
    for trial in run.trials:
        for cycle in trial.cycles:
            if run.session is not None:
                local = cycle.position.frame_time + run.session.offset
                day = local % 86400
            else:
                when = datetime.fromisoformat(cycle.wall_clock)
                day = when.hour * 3600 + when.minute * 60 + when.second
                local = None
            if abs(day - second_of_day) <= 1.0:
                if local is not None:
                    return trial, cycle.position.frame_time + (second_of_day - day)
                return trial, cycle.position.frame_time
    return None


def _render_record_note() -> list[str]:
    return [
        "",
        "## Is the Trial record the weak link?",
        "",
        (
            "For the planned move, no: each cycle row already carries its whole "
            "Movement Plan with every component's planned start and end, which is "
            "all the per-move half of this report reads. Key times are compiled in "
            "Main Process at dispatch (ADR 0002), out of the Engine that writes the "
            "record, so the record has none; since #538 the Session has them "
            "(`key.down`/`key.up`, by Correlation ID, on the record's clock), and "
            "this report reads them from there. A Session from before #538 has "
            "none, and its moves are judged from the reads alone."
        ),
    ]


# --- the plot ---------------------------------------------------------------------

_VERDICT_STYLE: Final = {
    "ok": ("o", "#2a9d2a"),
    "short": ("v", "#e08a00"),
    "long": ("^", "#e08a00"),
    "fell": ("x", "#d62728"),
    "off": ("s", "#d62728"),
    "no take-off": ("D", "#8a3ab9"),
    "not reached": ("d", "#8a3ab9"),
}


def plot_route(run: Run, path: Path, footholds: bool = True) -> str | None:
    """Draw the route; returns a note when the map's footholds were not drawn."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    note: str | None = None
    fig, ax = plt.subplots(figsize=(9, 14))
    if footholds and run.header is not None:
        try:
            from maple.model.world import WorldMap

            world = WorldMap.load(
                run.header.map_id if run.header.map_id is not None else run.header.map
            )
            for platform in world.platforms:
                for fh in platform.footholds:
                    ax.plot(
                        (fh.x1, fh.x2),
                        (fh.y1, fh.y2),
                        color="#999999",
                        lw=0.8,
                        zorder=1,
                    )
            for rope in world.ropes:
                ax.plot(
                    (rope.x, rope.x),
                    (rope.y1, rope.y2),
                    color="#a0522d",
                    lw=0.8,
                    ls="--",
                    zorder=1,
                )
        except Exception as error:  # the store is optional: the route still draws
            note = f"footholds not drawn ({type(error).__name__})"
    colors = ["#1f77b4", "#9467bd", "#17becf", "#bcbd22"]
    for i, trial in enumerate(run.trials):
        xs: list[float] = []
        ys: list[float] = []
        for k, read in enumerate(trial.reads):
            if k and math.dist((read.x, read.y), (xs[-1], ys[-1])) >= PORTAL_STEP:
                xs.append(math.nan)  # a portal: no line across the map
                ys.append(math.nan)
            xs.append(read.x)
            ys.append(read.y)
        ax.plot(
            xs,
            ys,
            color=colors[i % len(colors)],
            lw=1.0,
            alpha=0.7,
            label=trial.trial,
            zorder=2,
        )
        for j in run.judged[trial.trial]:
            if (
                j.move is None
                or j.kind == "portal"
                or (j.kind == "walk" and j.verdict == "en route")
            ):
                continue
            ax.plot(
                (j.move.start[0], j.move.end[0]),
                (j.move.start[1], j.move.end[1]),
                color="black",
                lw=0.6,
                ls=":",
                zorder=3,
            )
            style = _VERDICT_STYLE.get(j.verdict.split(",")[0])
            if style is not None and j.landing is not None:
                ax.scatter(
                    [j.landing[0]],
                    [j.landing[1]],
                    marker=style[0],
                    color=style[1],
                    s=28,
                    zorder=4,
                )
    for cluster in run.clusters:
        ax.annotate(
            f"C{cluster.number} x{len(cluster.tries)}",
            cluster.move.end,
            textcoords="offset points",
            xytext=(8, 8),
            color="#d62728",
            fontsize=9,
            zorder=5,
        )
    ax.invert_yaxis()
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x (virtual px)")
    ax.set_ylabel("y (virtual px)")
    ax.set_title(
        f"{run.header.schedule if run.header else run.label}: route, planned moves (dotted), landings"
    )
    handles, _ = ax.get_legend_handles_labels()
    for verdict in ("ok", "short", "long", "fell", "off", "no take-off"):
        marker, color = _VERDICT_STYLE[verdict]
        handles.append(
            ax.scatter([], [], marker=marker, color=color, s=28, label=verdict)
        )
    ax.legend(handles=handles, loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return note


# --- entry point ------------------------------------------------------------------


def _run_arg(value: str) -> tuple[Path, Path | None]:
    if "=" in value:
        record, session = value.split("=", 1)
        return Path(record), Path(session)
    return Path(value), None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("record", type=Path, help="A Trial record (JSONL).")
    parser.add_argument(
        "session", type=Path, nargs="?", help="The Session directory that ran it."
    )
    parser.add_argument(
        "--compare",
        action="append",
        default=[],
        help="Another record, or record=session.",
    )
    parser.add_argument(
        "--moment", action="append", default=[], help="HH:MM:SS or trial@seconds."
    )
    parser.add_argument(
        "--out", type=Path, help="The Markdown report (default: next to the record)."
    )
    parser.add_argument(
        "--no-footholds",
        action="store_true",
        help="Do not load the map from the game data.",
    )
    args = parser.parse_args(argv)

    run = analyze(args.record, args.session, label=args.record.stem)
    others = [analyze(r, s, label=r.stem) for r, s in map(_run_arg, args.compare)]
    out = args.out or args.record.with_suffix(".report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    plot = out.with_name(
        out.name.replace(".report.md", "").replace(".md", "") + ".route.png"
    )
    note = plot_route(run, plot, footholds=not args.no_footholds)
    text = render(run, others, args.moment, plot)
    if note:
        text += f"\nPlot: {note}.\n"
    out.write_text(text, encoding="utf-8")
    print(f"Wrote {out} and {plot}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
