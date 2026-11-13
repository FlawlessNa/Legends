"""
The physics schedule's analyzer: Trial records in, Calibration constants out.

`configs/trials/physics.json` tags each Trial with what it measures (`Measure`).
This reads a run's records offline, Trial by Trial, against the map's `WorldMap`,
and measures:

* **walk** - the walk speed: the steady stretches of consecutive reads on one
  platform, each stretch's first and last interval dropped (starting and
  stopping), horizontal px over seconds.
* **climb** - the climb speed, likewise on one rope or ladder, vertical.
* **jump** - each flight between two platforms: a parabola fitted to the reads
  above the take-off's height gives the rise, so the take-off speed (with the
  game's gravity); the reads either side bracket the flight time, which is
  checked against the time `VRPhysics` derives (the flight #396 holds a jump's
  keys for); a line through the airborne reads gives the speed sideways.
* **rope_jump** - each flight off a rope: whether it rose above its take-off, and
  how fast it started up (`ROPE_JUMP_SPEED`).
* **teleport** - each read-to-read jump too far for any other move, by direction:
  its reach.
* **drop** - each landing on a lower platform under the one taken off from: its
  height (`DROP_REACH`).

**Only ``fused`` reads count.** A ``coarse`` read (the minimap's alone) is 16 px
wide, too coarse for a speed. Unsure reads carry no position at all.

**Rate versus feasibility** (#13 in epic #6). The walk and climb speeds are rates:
an error there self-corrects on the next cycle. The jump arc, the teleport reach
and the drop reach are feasibility: an optimistic value plans a move the
character can't make, every cycle, which is a stuck-loop. So feasibility values
are rounded toward conservative: the jump and teleport constants take the
*smallest* measurement and round *down*, and so does the walk constant, because
the walk speed also scales the jump's reach. Only the climb constant, a pure
rate, rounds to the nearest.

The constants are multipliers on the game-file derivations (`Calibration`,
`CONTEXT.md`), computed from the speeds as measured and the header's
`Physics.img` values and stat multipliers, so they don't depend on the constants
the sitting itself ran with. `DROP_REACH` and `ROPE_JUMP_SPEED` are not
Calibration constants but `FootholdGraph` constants: the report says what the
records support, and a human edits them.

Run it on a record::

    python -m maple.calibration.analysis trial_records/<file>.jsonl

It needs the game data store, for the map and, when the header has none, the
`Physics.img` values.
"""

from __future__ import annotations

import argparse
import itertools
import math
import statistics
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import numpy as np

from game_data.catalogue import Rope
from maple.calibration.records import (
    CycleRecord,
    Phase,
    Record,
    SampleRecord,
    ScheduleHeader,
    TrialOutcome,
    TrialResult,
    read_records,
)
from maple.calibration.specs import Measure
from maple.model.mechanics.physics import (
    CLIMB_SPEED,
    TELEPORT_REACH,
    Calibration,
    VRPhysics,
)
from maple.model.navigation import DROP_REACH
from maple.model.navigation.foothold_graph import ROPE_JUMP_SPEED
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionSource

#: How far, in virtual px, a read may lie off a platform or a rope and still be
#: on it: the fused read's 2 px (#302 acceptance criterion 5), plus one.
SURFACE_TOL: Final = 3.0

#: How far a read on a rope may lie off its x, virtual px: a rope is a line, and
#: the feet hang about it.
ROPE_TOL: Final = 4.0

#: The longest gap between two reads, in seconds, that still counts as one
#: interval. Reads come every 0.1 s; a longer gap is a missed read, and a speed
#: across it would average over whatever happened unseen.
MAX_GAP: Final = 0.3

#: The longest gap between two reads, in seconds, that still counts as one
#: interval of a *steady* walk or climb. The Trial runner reads once per decision
#: cycle, which a live run (2026-11-13, 4 walks, 124 reads) measured at 0.32 s
#: apart, up to 0.57 s when a read was slow: not the 0.1 s `MAX_GAP` assumed. So
#: this is twice the cadence, rounded up, which takes in the slowest read seen
#: with room to spare. A speed over a gap this long is still a rate: the interval
#: has to start and end on one surface, move at least `MOVING_PX` and keep the
#: run's direction, so a stop or a turn inside it is not averaged in. Flights and
#: teleports keep `MAX_GAP`: a gap that long would hide the flight itself.
STEADY_GAP: Final = 0.75

#: How many steady intervals a walk or climb speed needs before it is trusted.
MIN_STEADY: Final = 3

#: The least movement, in virtual px, between two reads that counts as moving:
#: above the fused read's jitter.
MOVING_PX: Final = 3.0

#: How far above its take-off a flight off a rope has to rise to count as rising:
#: twice the fused read's 2 px.
RISE_PX: Final = 4.0

#: How much further than any other move could go, in virtual px, a read-to-read
#: jump has to be to count as a teleport: 3 canvas px.
TELEPORT_MIN: Final = 48.0

#: How far sideways a drop may land from its take-off, virtual px: a drop goes
#: straight down, so anything further is a fall off an end.
DROP_DRIFT: Final = 32.0

#: How far below its take-off a level jump may land, virtual px, for its flight
#: to be read off the parabola rather than only bracketed.
LEVEL_PX: Final = 8.0


# --- reading the records ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Read:
    """One fused read: when its frame was captured, and the feet, virtual px."""

    t: float
    x: float
    y: float


@dataclass
class TrialReads:
    """A measured Trial's fused reads, in frame order, and how it ended."""

    batch: str
    trial: str
    measures: Measure | None
    result: str | None = None
    reads: list[Read] = field(default_factory=list)


def trial_reads(records: Iterable[Record]) -> list[TrialReads]:
    """
    Every Trial's fused reads from its measured phase, cycles and samples
    together, in frame order. A Trial's ``measures`` and result come from its
    outcome; a Trial with none (the file was cut short) is listed with neither.
    """
    trials: dict[tuple[str, str], TrialReads] = {}
    for record in records:
        if isinstance(record, TrialOutcome):
            key = (record.batch, record.trial)
            entry = trials.setdefault(key, TrialReads(*key, None))
            entry.measures = (
                None if record.measures is None else Measure(record.measures)
            )
            entry.result = record.result
            continue
        if not isinstance(record, CycleRecord | SampleRecord):
            continue
        key = (record.batch, record.trial)
        entry = trials.setdefault(key, TrialReads(*key, None))
        position = record.position
        if (
            record.phase != Phase.MEASURING
            or position.position is None
            or position.source != PositionSource.FUSED.value
        ):
            continue
        entry.reads.append(Read(position.frame_time, *position.position))
    for entry in trials.values():
        entry.reads.sort(key=lambda read: read.t)
        # One frame read twice (a cycle and a sample) is one read.
        entry.reads = [
            read
            for i, read in enumerate(entry.reads)
            if i == 0 or read.t != entry.reads[i - 1].t
        ]
    return list(trials.values())


class Surfaces:
    """Which platform or rope of a map a read stands on, if any."""

    def __init__(self, world_map: WorldMap) -> None:
        self.platforms = world_map.platforms
        self.ropes = world_map.ropes

    def at(self, x: float, y: float) -> Platform | Rope | None:
        """The platform under the feet, else the rope they hang on, else `None`."""
        for platform in self.platforms:
            if platform.left - SURFACE_TOL <= x <= platform.right + SURFACE_TOL:
                level = platform.y_at(min(max(x, platform.left), platform.right))
                if level is not None and abs(level - y) <= SURFACE_TOL:
                    return platform
        for rope in self.ropes:
            if (
                abs(rope.x - x) <= ROPE_TOL
                and rope.y1 - SURFACE_TOL <= y <= rope.y2 + SURFACE_TOL
            ):
                return rope
        return None

    @staticmethod
    def level(surface: Platform | Rope, read: Read) -> float:
        """The y the feet stand at on ``surface``: the platform's, or the read's."""
        if isinstance(surface, Platform):
            level = surface.y_at(min(max(read.x, surface.left), surface.right))
            if level is not None:
                return level
        return read.y


# --- the measurements -------------------------------------------------------------


@dataclass(frozen=True)
class Speed:
    """A steady speed, virtual px/s, and what it was measured over."""

    speed: float
    seconds: float
    intervals: int


@dataclass(frozen=True)
class Flight:
    """
    One flight, from the last read on its take-off surface to the first on its
    landing surface.

    :ivar rise: Virtual px the fitted arc tops out above the take-off; `None`
        with too few reads above the take-off to fit.
    :ivar up_speed: The take-off speed upward that rise needs, under the game's
        gravity; 0 when it never rose.
    :ivar flight_low: The shortest the flight can have been: first to last
        airborne read.
    :ivar flight_high: The longest: last read before to first read after.
    :ivar flight_fit: The flight off the fitted arc, for a level jump.
    :ivar planned: The flight `VRPhysics` derives for this take-off and landing.
    :ivar side_speed: Virtual px/s sideways in the air.
    """

    trial: str
    take_off: tuple[float, float]
    landing: tuple[float, float]
    rise: float | None
    up_speed: float | None
    gravity_fit: float | None
    flight_low: float
    flight_high: float
    flight_fit: float | None
    planned: float
    side_speed: float | None

    @property
    def drop(self) -> float:
        return self.landing[1] - self.take_off[1]

    @property
    def planned_in_bracket(self) -> bool:
        return self.flight_low <= self.planned <= self.flight_high


@dataclass(frozen=True)
class Teleport:
    """One teleport seen between two reads: its direction and reach, virtual px."""

    trial: str
    direction: str
    reach: float


@dataclass(frozen=True)
class Drop:
    """One drop: where it took off and landed, and how far down, virtual px."""

    trial: str
    take_off: tuple[float, float]
    landing: tuple[float, float]

    @property
    def height(self) -> float:
        return self.landing[1] - self.take_off[1]


def steady_speed(
    reads: Sequence[Read], surfaces: Surfaces, *, vertical: bool, on_rope: bool
) -> list[tuple[float, float, float]]:
    """
    The steady intervals of ``reads``: ``(distance, path length, seconds)`` of each
    interval inside a run of moving intervals on one surface, each run's first and
    last interval dropped. An interval is two reads at most `STEADY_GAP` apart.
    """
    kept: list[tuple[float, float, float]] = []
    run: list[tuple[float, float, float]] = []
    sign = 0

    def close() -> None:
        kept.extend(run[1:-1])
        run.clear()

    for a, b in itertools.pairwise(reads):
        dt = b.t - a.t
        surface = surfaces.at(a.x, a.y)
        moved = (b.y - a.y) if vertical else (b.x - a.x)
        same = (
            surface is not None
            and isinstance(surface, Rope) == on_rope
            and surfaces.at(b.x, b.y) == surface
        )
        step_sign = (moved > 0) - (moved < 0)
        if not (same and 0 < dt <= STEADY_GAP and abs(moved) >= MOVING_PX):
            close()
            sign = 0
            continue
        if run and step_sign != sign:
            close()
        sign = step_sign
        run.append((abs(moved), math.hypot(b.x - a.x, b.y - a.y), dt))
    close()
    return kept


def flights(
    trial: str,
    reads: Sequence[Read],
    surfaces: Surfaces,
    physics: VRPhysics,
    *,
    off_rope: bool,
) -> list[Flight]:
    """Every flight in ``reads`` from a platform (or, ``off_rope``, a rope)."""
    found: list[Flight] = []
    on = [surfaces.at(read.x, read.y) for read in reads]
    i = 0
    while i < len(reads) - 2:
        source = on[i]
        if (
            source is None
            or on[i + 1] is not None
            or isinstance(source, Rope) != off_rope
        ):
            i += 1
            continue
        j = i + 1
        while j < len(reads) and on[j] is None:
            j += 1
        if j == len(reads) or any(
            b.t - a.t > MAX_GAP
            for a, b in zip(reads[i:j], reads[i + 1 : j + 1], strict=False)
        ):
            i = j
            continue
        landing_surface = on[j]
        assert landing_surface is not None
        airborne = reads[i + 1 : j]
        y0 = Surfaces.level(source, reads[i])
        y_land = Surfaces.level(landing_surface, reads[j])
        found.append(
            _flight(trial, reads[i], reads[j], airborne, y0, y_land, physics, off_rope)
        )
        i = j
    return found


def _flight(
    trial: str,
    before: Read,
    after: Read,
    airborne: Sequence[Read],
    y0: float,
    y_land: float,
    physics: VRPhysics,
    off_rope: bool,
) -> Flight:
    t0 = airborne[0].t
    above = [read for read in airborne if read.y <= y0 + SURFACE_TOL]
    rise = up_speed = gravity_fit = flight_fit = None
    if len(above) >= 3:
        a, b, c = np.polyfit([r.t - t0 for r in above], [r.y for r in above], 2)
        if a > 0:
            apex = c - b * b / (4 * a)
            rise = max(0.0, y0 - apex)
            up_speed = math.sqrt(2 * physics.gravity * rise)
            gravity_fit = 2 * a
            discriminant = b * b - 4 * a * (c - y0)
            if abs(y_land - y0) <= LEVEL_PX and discriminant > 0:
                flight_fit = math.sqrt(discriminant) / a
    if off_rope and rise is None:
        top = min(read.y for read in airborne)
        rise = max(0.0, y0 - top)
        up_speed = math.sqrt(2 * physics.gravity * rise)
    side_speed = None
    if len(airborne) >= 2:
        slope = np.polyfit([r.t - t0 for r in airborne], [r.x for r in airborne], 1)[0]
        side_speed = abs(float(slope))
    drop = y_land - y0
    if off_rope:
        lift = ROPE_JUMP_SPEED**2 / (2 * physics.gravity)
        planned = ROPE_JUMP_SPEED / physics.gravity + physics.fall_time(
            max(0.0, lift + drop)
        )
    else:
        planned = physics.jump_landing_time(max(drop, -physics.jump_height))
    return Flight(
        trial=trial,
        take_off=(before.x, y0),
        landing=(after.x, y_land),
        rise=rise,
        up_speed=up_speed,
        gravity_fit=gravity_fit,
        flight_low=airborne[-1].t - airborne[0].t,
        flight_high=after.t - before.t,
        flight_fit=flight_fit,
        planned=planned,
        side_speed=side_speed,
    )


def teleports(
    trial: str, reads: Sequence[Read], physics: VRPhysics
) -> tuple[list[Teleport], int]:
    """
    Every read-to-read jump too far for a walk, a jump or a fall, and how many
    were skipped as several casts in one interval.
    """
    found: list[Teleport] = []
    skipped = 0
    steps = list(itertools.pairwise(reads))

    def side_speed(k: int) -> float:
        """The x speed of the interval ``k``, when it is an ordinary one."""
        if not 0 <= k < len(steps):
            return 0.0
        a, b = steps[k]
        dt = b.t - a.t
        if (
            not 0 < dt <= MAX_GAP
            or abs(b.x - a.x) > physics.walk_speed * dt + TELEPORT_MIN
        ):
            return 0.0
        return abs(b.x - a.x) / dt

    for k, (a, b) in enumerate(steps):
        dt = b.t - a.t
        if not 0 < dt <= MAX_GAP:
            continue
        dx, dy = b.x - a.x, b.y - a.y
        excess = {
            "left" if dx < 0 else "right": abs(dx) - physics.walk_speed * dt,
            "up": -dy - physics.jump_speed * dt,
            "down": dy - physics.fall_speed * dt,
        }
        direction, over = max(excess.items(), key=lambda item: item[1])
        if over <= TELEPORT_MIN:
            continue
        if direction in ("left", "right"):
            if abs(dx) > 1.5 * physics.teleport_reach:
                skipped += 1
                continue
            walked = statistics.median([side_speed(k - 1), side_speed(k + 1)]) * dt
            found.append(Teleport(trial, direction, abs(dx) - walked))
        else:
            found.append(Teleport(trial, direction, abs(dy)))
    return found, skipped


def drops(trial: str, reads: Sequence[Read], surfaces: Surfaces) -> list[Drop]:
    """Every landing on a lower platform, under the platform taken off from."""
    found: list[Drop] = []
    standing = [
        (read, surface)
        for read in reads
        if isinstance(surface := surfaces.at(read.x, read.y), Platform)
    ]
    for (a, source), (b, target) in itertools.pairwise(standing):
        if target == source or abs(b.x - a.x) > DROP_DRIFT:
            continue
        if not source.left <= b.x <= source.right:
            continue
        top, bottom = Surfaces.level(source, a), Surfaces.level(target, b)
        if bottom > top + SURFACE_TOL:
            found.append(Drop(trial, (a.x, top), (b.x, bottom)))
    return found


# --- the report -------------------------------------------------------------------


@dataclass
class CalibrationReport:
    """What a physics run measured, and the constants it supports."""

    walk: Speed | None
    climb: Speed | None
    jumps: list[Flight]
    rope_jumps: list[Flight]
    teleports: list[Teleport]
    teleports_skipped: int
    drops: list[Drop]
    outcomes: dict[str, list[tuple[str, str | None]]]
    constants: dict[str, float]
    rope_jump_speed: float | None
    drop_reach: float | None
    notes: list[str]


def analyze(
    records: Sequence[Record],
    world_map: WorldMap,
    game_physics: dict[str, float],
) -> CalibrationReport:
    """
    Measure a physics run.

    :param records: The run's records, header first.
    :param world_map: The map it ran on.
    :param game_physics: `Physics.img`'s values, when the header carries none.
    """
    header = next((r for r in records if isinstance(r, ScheduleHeader)), None)
    values = (header.physics if header and header.physics else None) or game_physics
    speed_x = (header.speed_multiplier if header else None) or 1.0
    jump_x = (header.jump_multiplier if header else None) or 1.0
    in_force = Calibration(**(header.calibration or {})) if header else Calibration()
    physics = VRPhysics.from_game_files(
        values, speed_multiplier=speed_x, jump_multiplier=jump_x, calibration=in_force
    )
    surfaces = Surfaces(world_map)

    walk_gaps: list[float] = []
    climb_gaps: list[float] = []
    walk_steps: list[tuple[float, float, float]] = []
    climb_steps: list[tuple[float, float, float]] = []
    jumps: list[Flight] = []
    rope_jumps: list[Flight] = []
    seen_teleports: list[Teleport] = []
    skipped = 0
    seen_drops: list[Drop] = []
    outcomes: dict[str, list[tuple[str, str | None]]] = {}
    for entry in trial_reads(records):
        if entry.measures is None:
            continue
        outcomes.setdefault(entry.measures.value, []).append(
            (entry.trial, entry.result)
        )
        reads = entry.reads
        match entry.measures:
            case Measure.WALK:
                walk_gaps += _gaps(reads)
                walk_steps += steady_speed(
                    reads, surfaces, vertical=False, on_rope=False
                )
            case Measure.CLIMB:
                climb_gaps += _gaps(reads)
                climb_steps += steady_speed(
                    reads, surfaces, vertical=True, on_rope=True
                )
            case Measure.JUMP:
                jumps += flights(entry.trial, reads, surfaces, physics, off_rope=False)
            case Measure.ROPE_JUMP:
                rope_jumps += flights(
                    entry.trial, reads, surfaces, physics, off_rope=True
                )
            case Measure.TELEPORT:
                found, missed = teleports(entry.trial, reads, physics)
                seen_teleports += found
                skipped += missed
            case Measure.DROP:
                seen_drops += drops(entry.trial, reads, surfaces)

    walk = _speed(walk_steps)
    climb = _speed(climb_steps)
    constants: dict[str, float] = {}
    notes: list[str] = []
    if walk is not None:
        constants["walk"] = _floor(walk.speed / (values["walkSpeed"] * speed_x))
    else:
        notes.append(
            f"No steady walk was read: no walk constant. {_STEADY}{_cadence(walk_gaps)}"
        )
    if climb is not None:
        constants["climb"] = round(climb.speed / (CLIMB_SPEED * speed_x), 2)
    else:
        notes.append(
            f"No steady climb was read: no climb constant. {_STEADY}"
            f"{_cadence(climb_gaps)}"
        )
    take_offs = [f.up_speed for f in jumps if f.up_speed is not None and f.gravity_fit]
    if take_offs:
        constants["jump"] = _floor(min(take_offs) / (values["jumpSpeed"] * jump_x))
    else:
        notes.append(
            "No jump had enough reads above its take-off to fit: no jump constant."
        )
    sideways = [t.reach for t in seen_teleports if t.direction in ("left", "right")]
    if sideways:
        constants["teleport"] = _floor(min(sideways) / TELEPORT_REACH)
    else:
        notes.append(
            "No sideways teleport was seen (no Teleport skill, or none planned): "
            "no teleport constant."
        )
    for direction in ("up", "down"):
        reach = [t.reach for t in seen_teleports if t.direction == direction]
        if not reach:
            notes.append(f"No teleport {direction} was seen.")
        elif max(reach) < physics.teleport_reach - SURFACE_TOL:
            notes.append(
                f"Teleports {direction} reached at most {max(reach):.0f} virtual px; the "
                f"graph plans them up to {physics.teleport_reach:.0f}. A teleport {direction} "
                "lands on the platform it is aimed at, so this is a lower bound, unless "
                "one of them failed to arrive."
            )
    for flight in jumps:
        if not flight.planned_in_bracket:
            notes.append(
                f"{flight.trial}: the planned flight, {flight.planned:.3f} s, is outside "
                f"the measured {flight.flight_low:.3f}-{flight.flight_high:.3f} s."
            )
    side = [f.side_speed for f in jumps if f.side_speed is not None]
    if side and min(side) < physics.walk_speed - MOVING_PX / 0.1:
        notes.append(
            f"The slowest jump moved {min(side):.0f} virtual px/s sideways, against the "
            f"walk speed's {physics.walk_speed:.0f}: the graph's jump reach assumes the "
            "walk speed in the air, so it is optimistic for those jumps."
        )

    rope_jump_speed: float | None = None
    if rope_jumps:
        rising = [f.up_speed or 0.0 for f in rope_jumps if (f.rise or 0.0) > RISE_PX]
        rope_jump_speed = (
            math.floor(min(rising) / 10) * 10.0
            if len(rising) == len(rope_jumps)
            else 0.0
        )
    else:
        notes.append("No jump off a rope was read: ROPE_JUMP_SPEED is unmeasured.")
    drop_reach: float | None = None
    if seen_drops:
        highest = max(d.height for d in seen_drops)
        drop_reach = math.floor(highest / 10) * 10.0
        if highest < DROP_REACH - MOVING_PX:
            notes.append(
                f"Drops landed from up to {highest:.0f} virtual px; DROP_REACH is "
                f"{DROP_REACH:.0f}, unverified above that."
            )
    else:
        notes.append("No drop was read: DROP_REACH is unmeasured.")
    for measure, trials in outcomes.items():
        failed = [name for name, result in trials if result != TrialResult.ARRIVED]
        if failed:
            notes.append(
                f"{measure}: {len(failed)} of {len(trials)} Trial(s) did not arrive "
                f"({', '.join(failed)}); for a feasibility measure, that move may be "
                "beyond reach."
            )
    return CalibrationReport(
        walk=walk,
        climb=climb,
        jumps=jumps,
        rope_jumps=rope_jumps,
        teleports=seen_teleports,
        teleports_skipped=skipped,
        drops=seen_drops,
        outcomes=outcomes,
        constants=constants,
        rope_jump_speed=rope_jump_speed,
        drop_reach=drop_reach,
        notes=notes,
    )


def render(report: CalibrationReport) -> str:
    """The report as text, ending with the profile's ``calibration:`` block."""
    lines: list[str] = []
    for label, speed in (("Walk", report.walk), ("Climb", report.climb)):
        if speed is not None:
            lines.append(
                f"{label} speed: {speed.speed:.1f} virtual px/s "
                f"({speed.intervals} intervals, {speed.seconds:.1f} s)"
            )
    for title, group in (
        ("Jumps", report.jumps),
        ("Jumps off a rope", report.rope_jumps),
    ):
        if group:
            lines.append(f"{title}:")
        for f in group:
            lines.append(
                f"  {f.trial}: drop {f.drop:+.0f}, rise {_num(f.rise)}, up "
                f"{_num(f.up_speed)} px/s, gravity fit {_num(f.gravity_fit)}, flight "
                f"{f.flight_low:.3f}-{f.flight_high:.3f} s (fit {_num(f.flight_fit, 3)}, "
                f"planned {f.planned:.3f}), sideways {_num(f.side_speed)} px/s"
            )
    if report.teleports:
        lines.append("Teleports:")
        for direction in ("left", "right", "up", "down"):
            reach = [t.reach for t in report.teleports if t.direction == direction]
            if reach:
                lines.append(
                    f"  {direction}: {len(reach)}, reach {min(reach):.0f}-{max(reach):.0f}"
                )
        if report.teleports_skipped:
            lines.append(f"  skipped as several casts: {report.teleports_skipped}")
    if report.drops:
        lines.append(
            "Drops landed: "
            + ", ".join(
                f"{d.height:.0f}" for d in sorted(report.drops, key=lambda d: d.height)
            )
        )
    lines.append(
        "ROPE_JUMP_SPEED supported: "
        + (
            "unmeasured"
            if report.rope_jump_speed is None
            else f"{report.rope_jump_speed:.0f}"
        )
    )
    lines.append(
        "DROP_REACH verified to: "
        + ("unmeasured" if report.drop_reach is None else f"{report.drop_reach:.0f}")
    )
    for measure, trials in report.outcomes.items():
        arrived = sum(1 for _, result in trials if result == TrialResult.ARRIVED)
        lines.append(f"{measure}: {arrived}/{len(trials)} arrived")
    lines += [f"Note: {note}" for note in report.notes]
    lines.append("calibration:")
    lines += [f"  {key}: {value:.2f}" for key, value in report.constants.items()]
    return "\n".join(lines) + "\n"


_STEADY = (
    f"A steady speed needs at least {MIN_STEADY} intervals: two fused reads at most "
    f"{STEADY_GAP} s apart, on one platform (or rope), at least {MOVING_PX:g} px "
    "apart and in one direction, with the first and last interval of each such run "
    "dropped."
)


def _gaps(reads: Sequence[Read]) -> list[float]:
    return [b.t - a.t for a, b in itertools.pairwise(reads)]


def _cadence(gaps: Sequence[float]) -> str:
    """What the reads' spacing was, when it explains a run with no steady speed."""
    if not gaps:
        return " The measured Trials had no fused reads at all."
    return (
        f" Those Trials' reads were a median of {statistics.median(gaps):.2f} s apart "
        f"(longest {max(gaps):.2f} s)."
    )


def _speed(steps: list[tuple[float, float, float]]) -> Speed | None:
    if len(steps) < MIN_STEADY:
        return None
    seconds = sum(step[2] for step in steps)
    return Speed(sum(step[0] for step in steps) / seconds, seconds, len(steps))


def _floor(value: float) -> float:
    """Down to the hundredth: toward conservative."""
    return math.floor(value * 100 + 1e-9) / 100


def _num(value: float | None, digits: int = 0) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Turn a physics Trial record into Calibration constants."
    )
    parser.add_argument("record", type=Path, help="A Trial record (JSONL).")
    args = parser.parse_args(argv)
    records = read_records(args.record)
    header = next((r for r in records if isinstance(r, ScheduleHeader)), None)
    if header is None:
        raise SystemExit(f"{args.record} has no header.")
    world_map = WorldMap.load(
        header.map_id if header.map_id is not None else header.map
    )
    if header.physics:
        values = header.physics
    else:
        from maple.model.mechanics.physics import game_physics

        values = game_physics()
    sys.stdout.write(render(analyze(records, world_map, values)))


if __name__ == "__main__":
    main()
