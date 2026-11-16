"""
The physics schedule's analyzer, on synthetic records over a synthetic map.

Each stream below is drawn from a known motion - a walk at 150 px/s, a jump
taking off at 500 px/s under the game's gravity - sampled every 0.1 s as the
runner samples, at an offset so no read falls on a take-off or a landing. The
checks assert the analyzer recovers that motion, and turns it into the
Calibration constants it implies, rounded the way #13's rate-versus-feasibility
rule says: feasibility down, from the smallest measurement.

Nothing here says the real client moves like this. That is what the live sitting
on `configs/trials/physics.json` is for.
"""

import math
from collections.abc import Callable, Sequence

import pytest

from maple.calibration.analysis import (
    CalibrationReport,
    Surfaces,
    analyze,
    render,
    trial_reads,
)
from maple.calibration.records import (
    Phase,
    PositionRecord,
    Record,
    SampleRecord,
    ScheduleHeader,
    TrialOutcome,
    TrialResult,
)
from maple.calibration.specs import Knobs
from maple.model.world import Platform, WorldMap
from tests.test_maple.movement_lab.corpus import LAB_PHYSICS_VALUES
from tests.test_maple.movement_lab.fixture_maps import _footholds, _map, _rope

GRAVITY = LAB_PHYSICS_VALUES["gravityAcc"]

#: A floor, a second floor across a 50 px gap, a shelf 300 px above the first
#: floor's middle, and a rope hanging over the first floor's right end.
MAP = WorldMap.from_map_data(
    _map(
        900_000_101,
        "analysis_lab",
        _footholds((0, 0, 1000, 0), (1050, 0, 1400, 0), (200, -300, 600, -300)),
        (_rope(1, 800, -200, -40, ladder=False),),
    )
)

#: Seconds between reads, and the offset of the first: no read on an event.
STEP = 0.1
OFFSET = 0.03

type Motion = Callable[[float], tuple[float, float]]


def stream(
    motion: Motion, start: float, end: float
) -> list[tuple[float, float, float]]:
    """``(t, x, y)`` reads of ``motion`` from ``start`` to ``end`` seconds."""
    reads = []
    t = start + OFFSET
    while t <= end:
        reads.append((t, *motion(t)))
        t += STEP
    return reads


def records(
    trials: Sequence[tuple[str, str, list[tuple[float, float, float]]]],
    *,
    result: str = TrialResult.ARRIVED,
    calibration: dict[str, float] | None = None,
    source: str = "fused",
) -> list[Record]:
    """A record file: the header, then each Trial's samples and outcome."""
    out: list[Record] = [
        ScheduleHeader(
            "physics",
            "analysis_lab",
            "2026-01-01T00:00:00+00:00",
            "host",
            map_id=MAP.id,
            physics=dict(LAB_PHYSICS_VALUES),
            speed_multiplier=1.0,
            jump_multiplier=1.0,
            calibration=calibration,
        )
    ]
    for name, measures, reads in trials:
        for t, x, y in reads:
            out.append(
                SampleRecord(
                    "physics",
                    measures,
                    name,
                    str(Phase.MEASURING),
                    t,
                    PositionRecord("read", (round(x, 1), round(y, 1)), source, t),
                )
            )
        out.append(
            TrialOutcome(
                "physics",
                measures,
                name,
                Knobs(),
                (0, 0),
                (0, 0),
                16.0,
                30.0,
                result,
                1.0,
                None,
                10.0,
                10,
                0,
                0,
                0,
                "2026-01-01T00:00:00+00:00",
                measures=measures,
            )
        )
    return out


def run(
    *trials: tuple[str, str, list[tuple[float, float, float]]], **kw: object
) -> CalibrationReport:
    return analyze(records(trials, **kw), MAP, dict(LAB_PHYSICS_VALUES))  # type: ignore[arg-type]


# --- motions ----------------------------------------------------------------------


def walk(speed: float, x0: float = 50.0) -> list[tuple[float, float, float]]:
    """Stand 0.3 s, walk right at ``speed`` for 4 s, stand."""

    def at(t: float) -> tuple[float, float]:
        moving = min(max(t - 0.3, 0.0), 4.0)
        return x0 + speed * moving, 0.0

    return stream(at, 0.0, 5.0)


def climb(speed: float) -> list[tuple[float, float, float]]:
    """Up the rope from near its bottom, at ``speed``."""

    def at(t: float) -> tuple[float, float]:
        moving = min(max(t - 0.3, 0.0), 1.2)
        return 800.0, -50.0 - speed * moving

    return stream(at, 0.0, 1.8)


def jump(
    up: float,
    side: float = 125.0,
    x0: float = 990.0,
    y0: float = 0.0,
    off_rope: bool = False,
) -> list[tuple[float, float, float]]:
    """
    Stand, then take off at 0.45 s with ``up`` px/s upward and ``side`` px/s to the
    right, and fall until the floor at y 0 stops the fall.
    """
    take_off = 0.45

    def at(t: float) -> tuple[float, float]:
        if t < take_off:
            return x0, y0
        s = t - take_off
        y = y0 - up * s + GRAVITY * s * s / 2
        if y >= 0.0 and (s > 0.05 or off_rope):
            land = (up + math.sqrt(up * up + 2 * GRAVITY * -y0)) / GRAVITY
            return x0 + side * land, 0.0
        return x0 + side * s, y

    return stream(at, 0.0, 1.6)


def drop(height: float) -> list[tuple[float, float, float]]:
    """From the shelf at x 400 straight down onto the floor ``height`` below."""
    top = -height

    def at(t: float) -> tuple[float, float]:
        s = max(t - 0.5, 0.0)
        return 400.0, min(top + GRAVITY * s * s / 2, 0.0)

    return stream(at, 0.0, 1.5)


def teleport(reach: float) -> list[tuple[float, float, float]]:
    """Walk right at 125 px/s; at 1 s, teleport ``reach`` px right."""

    def at(t: float) -> tuple[float, float]:
        return 50.0 + 125.0 * t + (reach if t >= 1.0 else 0.0), 0.0

    return stream(at, 0.0, 2.0)


# --- reading the records ----------------------------------------------------------


def test_only_fused_reads_of_the_measured_phase_count() -> None:
    """A coarse read is 16 px wide: too coarse for a speed. Unsure has no number."""
    coarse = records([("w", "walk", walk(150.0))], source="coarse")
    (entry,) = trial_reads(coarse)
    assert entry.reads == []
    assert run(("w", "walk", walk(150.0))).walk is not None
    assert analyze(coarse, MAP, dict(LAB_PHYSICS_VALUES)).walk is None


def test_a_read_is_placed_on_its_platform_or_rope() -> None:
    surfaces = Surfaces(MAP)
    assert isinstance(surfaces.at(500.0, 1.5), Platform)
    assert surfaces.at(800.0, -120.0) == MAP.ropes[0]
    assert surfaces.at(1050.0, -30.0) is None


# --- rates ------------------------------------------------------------------------


def test_the_walk_speed_is_measured_and_rounded_down_into_its_constant() -> None:
    """
    150 px/s against `walkSpeed` 125 is 1.2. Rounded down: the walk speed also
    scales the jump's reach, a feasibility value.
    """
    report = run(("w1", "walk", walk(150.0)), ("w2", "walk", walk(131.3)))
    assert report.walk is not None
    assert report.walk.speed == pytest.approx((150.0 + 131.3) / 2, abs=1.0)
    assert report.constants["walk"] == math.floor(report.walk.speed / 125 * 100) / 100


def _walk_every(step: float, speed: float = 150.0) -> list[tuple[float, float, float]]:
    """A 4 s walk read every ``step`` seconds, as the runner's cycle reads it."""
    reads = []
    t = OFFSET
    while t <= 5.0:
        reads.append((t, 50.0 + speed * min(max(t - 0.3, 0.0), 4.0), 0.0))
        t += step
    return reads


def test_a_walk_read_at_the_runner_s_cycle_cadence_gives_its_constant() -> None:
    """
    The live run of 2026-11-13 read every 0.32 s (up to 0.57 s), not every 0.1 s:
    the steady walk must survive it, and give the same speed.
    """
    report = run(("w", "walk", _walk_every(0.32)))
    assert report.walk is not None
    assert report.walk.speed == pytest.approx(150.0, abs=0.5)
    assert report.constants["walk"] == 1.2


def test_a_walk_read_too_rarely_says_what_a_steady_walk_needs() -> None:
    report = run(("w", "walk", _walk_every(1.0)))
    assert report.walk is None
    text = render(report)
    assert "No steady walk was read" in text
    assert "at least 3 intervals" in text
    assert "0.75 s apart" in text
    assert "median of 1.00 s" in text


def test_standing_and_starting_are_not_counted_in_the_walk_speed() -> None:
    report = run(("w", "walk", walk(150.0)))
    assert report.walk is not None
    assert report.walk.speed == pytest.approx(150.0, abs=0.5)


def test_the_climb_speed_is_a_rate_rounded_to_the_nearest() -> None:
    report = run(("c", "climb", climb(100.0)))
    assert report.climb is not None
    assert report.climb.speed == pytest.approx(100.0, abs=0.5)
    assert report.constants["climb"] == 0.8


# --- feasibility ------------------------------------------------------------------


def test_the_jump_constant_is_the_smallest_take_off_rounded_down() -> None:
    """
    Two jumps taking off at 500 and 540 px/s against `jumpSpeed` 555: the smaller
    is 0.9009, which rounds down to 0.90. An optimistic jump constant plans jumps
    the character can't make, every cycle.
    """
    report = run(("j1", "jump", jump(540.0)), ("j2", "jump", jump(500.0)))
    assert len(report.jumps) == 2
    speeds = sorted(f.up_speed or 0.0 for f in report.jumps)
    assert speeds[0] == pytest.approx(500.0, rel=0.02)
    assert speeds[1] == pytest.approx(540.0, rel=0.02)
    assert report.constants["jump"] <= speeds[0] / 555
    assert report.constants["jump"] == pytest.approx(0.90, abs=0.011)


def test_a_jump_s_flight_is_bracketed_and_checked_against_the_physics() -> None:
    """
    The flight #396 holds a jump's keys for, derived from the physics in force,
    must fall inside what the reads allow: 2 x 500 / 2000 = 0.5 s here.
    """
    (flight,) = run(("j", "jump", jump(500.0))).jumps
    assert flight.flight_low <= 0.5 <= flight.flight_high
    assert flight.flight_fit == pytest.approx(0.5, abs=0.01)
    assert flight.side_speed == pytest.approx(125.0, abs=1.0)
    # Planned with the game's 555 px/s: 0.555 s, inside the bracket of 0.5.
    assert flight.planned == pytest.approx(0.555, abs=0.001)


def test_a_planned_flight_outside_the_measured_bracket_is_reported() -> None:
    report = run(("j", "jump", jump(500.0)), calibration={"jump": 1.4})
    (flight,) = report.jumps
    assert not flight.planned_in_bracket
    assert any("planned flight" in note for note in report.notes)


def test_a_slow_jump_sideways_is_reported_as_an_optimistic_reach() -> None:
    report = run(("j", "jump", jump(500.0, side=60.0, x0=500.0)))
    assert any("optimistic" in note for note in report.notes)


def test_a_jump_off_a_rope_that_rises_supports_a_rope_jump_speed() -> None:
    report = run(("r", "rope_jump", jump(150.0, x0=800.0, y0=-150.0, off_rope=True)))
    (flight,) = report.rope_jumps
    assert flight.rise == pytest.approx(150.0**2 / (2 * GRAVITY), abs=1.5)
    assert report.rope_jump_speed is not None
    assert 120.0 <= report.rope_jump_speed <= 150.0
    assert report.rope_jump_speed % 10 == 0


def test_a_jump_off_a_rope_that_does_not_rise_supports_none() -> None:
    report = run(("r", "rope_jump", jump(0.0, x0=800.0, y0=-150.0, off_rope=True)))
    assert len(report.rope_jumps) == 1
    assert report.rope_jump_speed == 0.0


def test_a_sideways_teleport_s_reach_takes_off_the_walk_around_it() -> None:
    report = run(
        ("t1", "teleport", teleport(150.0)), ("t2", "teleport", teleport(141.0))
    )
    reach = sorted(t.reach for t in report.teleports)
    assert reach == pytest.approx([141.0, 150.0], abs=1.0)
    assert report.constants["teleport"] == math.floor(reach[0] / 150 * 100) / 100


def test_drops_are_measured_and_drop_reach_is_reported_to_the_highest() -> None:
    report = run(("d", "drop", drop(300.0)))
    (seen,) = report.drops
    assert seen.height == pytest.approx(300.0, abs=1.0)
    assert report.drop_reach == 300.0
    assert any("unverified above" in note for note in report.notes)


def test_a_trial_that_did_not_arrive_is_reported() -> None:
    report = run(("d", "drop", drop(300.0)), result=TrialResult.TIMEOUT)
    assert any("did not arrive" in note for note in report.notes)


def test_what_was_not_measured_is_said_and_given_no_constant() -> None:
    report = run(("w", "walk", walk(150.0)))
    assert set(report.constants) == {"walk"}
    text = render(report)
    assert "No jump" in text
    assert "ROPE_JUMP_SPEED supported: unmeasured" in text
    assert text.endswith("calibration:\n  walk: 1.20\n")
