"""
The `TrialDriver`: every judgement a Trial makes, checked without a game client.

The driver is fed positions and a clock, so a whole schedule can be walked
deterministically here - which is the point of the seam. What these checks pin is
the part of the framework a live run cannot re-decide: that a Trial is measured from
its own start and not from wherever the character happened to be, that a budget ends
a Trial rather than a run, that the two defect counters count what they claim to,
and that a batch boundary hands the runner the next batch's Knobs.

`now` is always passed explicitly. Nothing here sleeps, and nothing here reads a
clock: a check that took real time to run would be a check that measures this
machine.
"""

import pytest

from botting.screen import Reading
from maple.calibration.driver import COARSE_SLACK, DefectPolicy, TrialDriver
from maple.calibration.records import (
    CycleRecord,
    ListSink,
    Phase,
    ScheduleHeader,
    TrialOutcome,
    TrialResult,
)
from maple.calibration.specs import (
    Knobs,
    Measure,
    TrialBatch,
    TrialSchedule,
    TrialSpec,
)
from maple.screen.position import PositionSource, VirtualPosition

#: The defect policy these checks run on: the virtual-px defaults are 16 and 8 px,
#: and the position streams below move a few px at a time, so they get a policy at
#: their own scale. The defaults have checks of their own (the end of the file).
SMALL = DefectPolicy(progress_epsilon=1.0, level_band=0.5)


def at(
    x: float, y: float, source: PositionSource = PositionSource.FUSED
) -> Reading[VirtualPosition]:
    """A read virtual position."""
    return Reading.read(VirtualPosition(x, y, source), 0.0)


def unsure() -> Reading[VirtualPosition]:
    return Reading.unsure(0.0, "two characters where the minimap puts ours")


def spec(
    name: str = "t",
    start: tuple[int, int] = (0, 0),
    target: tuple[int, int] = (10, 0),
    tolerance: float = 1.0,
    time_budget: float = 10.0,
    setup_budget: float | None = None,
    measures: Measure | None = None,
) -> TrialSpec:
    return TrialSpec(
        name, start, target, tolerance, time_budget, setup_budget, measures
    )


def schedule(*batches: TrialBatch) -> TrialSchedule:
    return TrialSchedule(
        "sched", "fixture-map", batches or (TrialBatch("b", (spec(),)),)
    )


def driver(
    sched: TrialSchedule | None = None, policy: DefectPolicy | None = None
) -> tuple[TrialDriver, ListSink]:
    sink = ListSink()
    return TrialDriver(sched or schedule(), sink, defects=policy or SMALL), sink


def cycles(sink: ListSink) -> list[CycleRecord]:
    return [r for r in sink if isinstance(r, CycleRecord)]


def outcomes(sink: ListSink) -> list[TrialOutcome]:
    return [r for r in sink if isinstance(r, TrialOutcome)]


# --- The header -------------------------------------------------------------------


def test_a_run_opens_with_a_header_naming_the_schedule_and_map() -> None:
    _, sink = driver()
    header = sink[0]
    assert isinstance(header, ScheduleHeader)
    assert header.schedule == "sched"
    assert header.map == "fixture-map"


# --- Positioning ------------------------------------------------------------------


def test_a_trial_aims_at_its_start_before_it_aims_at_its_target() -> None:
    """
    A Trial that began somewhere other than its `start` measured a different run.
    The walk there is a phase of the Trial, not a precondition someone remembered.
    """
    d, _ = driver()
    assert d.phase is Phase.POSITIONING
    assert d.target == (0, 0)

    d.advance(at(5, 0), 0.0)
    assert d.phase is Phase.POSITIONING

    d.advance(at(0, 0), 1.0)
    assert d.phase is Phase.MEASURING
    assert d.target == (10, 0)


def test_the_measured_clock_starts_when_the_character_reaches_the_start() -> None:
    """Time spent walking to `start` is not time-to-arrival."""
    d, sink = driver()
    d.advance(at(9, 0), 0.0)
    d.advance(at(0, 0), 30.0)  # arrived at `start`, 30s in
    d.advance(at(10, 0), 32.0)  # arrived at `target`, 2s later
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.ARRIVED
    assert outcome.time_to_arrival == 2.0


def test_the_positioning_phase_has_its_own_budget() -> None:
    d, sink = driver(
        schedule(TrialBatch("b", (spec(time_budget=10.0, setup_budget=3.0),)))
    )
    d.advance(at(9, 0), 0.0)
    d.advance(at(9, 0), 3.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.SETUP_FAILED


def test_a_trial_that_never_reached_its_start_reports_no_measurement() -> None:
    """
    `SETUP_FAILED` is not a slow arrival. A Trial whose character never got to its
    start has no time-to-arrival, and reporting one would fabricate a measurement.
    """
    d, sink = driver(schedule(TrialBatch("b", (spec(setup_budget=1.0),))))
    d.advance(at(9, 0), 0.0)
    d.advance(at(9, 0), 1.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.SETUP_FAILED
    assert outcome.time_to_arrival is None


def test_positioning_cycles_are_recorded_and_labelled() -> None:
    """
    Kept, not dropped: a schedule that failed because positioning never converged is
    diagnosed from these, and a phase label is what stops them being read as
    measurements.
    """
    d, sink = driver()
    d.advance(at(9, 0), 0.0)
    d.advance(at(0, 0), 1.0)
    d.advance(at(10, 0), 2.0)
    phases = [c.phase for c in cycles(sink)]
    assert phases == [Phase.POSITIONING, Phase.POSITIONING, Phase.MEASURING]


def test_a_character_already_at_the_start_measures_from_the_first_cycle() -> None:
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    assert d.phase is Phase.MEASURING
    d.advance(at(10, 0), 4.0)
    (outcome,) = outcomes(sink)
    assert outcome.time_to_arrival == 4.0


# --- Arrival and budget -----------------------------------------------------------


def test_arrival_is_inside_the_tolerance_not_exactly_on_the_target() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(tolerance=2.0),))))
    d.advance(at(0, 0), 0.0)
    d.advance(at(9, 1), 1.0)  # distance sqrt(2) < 2.0
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.ARRIVED
    assert outcome.final_error == pytest.approx(2**0.5)


def test_running_out_of_budget_ends_the_trial_and_records_how_far_off_it_was() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=5.0),))))
    d.advance(at(0, 0), 0.0)
    d.advance(at(7, 0), 5.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.TIMEOUT
    assert outcome.final_error == 3.0
    assert outcome.time_to_arrival is None


def test_the_arriving_cycle_is_recorded_before_the_trial_closes() -> None:
    """
    A file whose last cycle is the one *before* arrival cannot say how close the
    character actually got - which is the number the whole experiment is about.
    """
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    last = cycles(sink)[-1]
    assert last.position.position == (10.0, 0.0)
    assert last.error == 0.0
    assert last.dispatched is False


def test_the_cycle_count_covers_the_measured_phase_only() -> None:
    """
    Two Trials are compared on cycles-to-arrival. Folding in however many cycles the
    walk to `start` happened to need would make that comparison meaningless.
    """
    d, sink = driver()
    for t in range(4):
        d.advance(at(9, 0), float(t))  # four positioning cycles
    d.advance(at(0, 0), 4.0)  # the fifth, which arrives at `start`
    d.advance(at(5, 0), 5.0)
    d.advance(at(10, 0), 6.0)
    (outcome,) = outcomes(sink)
    assert outcome.cycles == 2
    assert len(cycles(sink)) == 7


# --- What the runner is told ------------------------------------------------------


def test_a_cycle_still_short_of_the_target_asks_for_a_dispatch() -> None:
    d, _ = driver()
    d.advance(at(0, 0), 0.0)
    verdict = d.advance(at(5, 0), 1.0)
    assert verdict.dispatch is True
    assert verdict.target == (10, 0)
    assert verdict.outcome is None


def test_an_arriving_cycle_asks_for_no_dispatch() -> None:
    """Sending a plan built for a target already reached is how a loop oscillates."""
    d, _ = driver()
    d.advance(at(0, 0), 0.0)
    verdict = d.advance(at(10, 0), 1.0)
    assert verdict.dispatch is False
    assert verdict.outcome is not None


def test_the_movement_plan_and_correlation_id_reach_the_record() -> None:
    """
    The Correlation ID is the join key into the Session's `action.*` telemetry - the
    only way a record reaches what compilation did with the plan, since compilation
    happens in another process.
    """
    from maple.calibration.records import MovementSummary

    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(
        at(5, 0),
        1.0,
        plan=(MovementSummary("WALK_RIGHT", 5, False, False),),
        correlation_id="abc",
    )
    last = cycles(sink)[-1]
    assert last.plan == (MovementSummary("WALK_RIGHT", 5, False, False),)
    assert last.correlation_id == "abc"


# --- Walking the schedule ---------------------------------------------------------


def test_trials_are_walked_in_order_and_the_run_then_finishes() -> None:
    sched = schedule(
        TrialBatch("first", (spec("one"), spec("two"))),
        TrialBatch("second", (spec("three"),)),
    )
    d, sink = driver(sched)
    for _ in range(3):
        d.advance(at(0, 0), 0.0)
        d.advance(at(10, 0), 1.0)
    assert [o.trial for o in outcomes(sink)] == ["one", "two", "three"]
    assert [o.batch for o in outcomes(sink)] == ["first", "first", "second"]
    assert d.finished
    assert d.target is None


def test_advancing_a_finished_schedule_records_nothing() -> None:
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    before = len(sink)
    verdict = d.advance(at(10, 0), 2.0)
    assert verdict.finished is True
    assert verdict.dispatch is False
    assert len(sink) == before


def test_each_trial_restarts_its_own_positioning_phase() -> None:
    """
    The second Trial is not measured from wherever the first one ended: it walks to
    its own start first, same as the first one did.
    """
    sched = schedule(
        TrialBatch(
            "b",
            (spec("one"), spec("two", start=(50, 0), target=(60, 0))),
        )
    )
    d, _ = driver(sched)
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    assert d.phase is Phase.POSITIONING
    assert d.target == (50, 0)


def test_a_batch_boundary_hands_over_that_batch_s_knobs() -> None:
    """What makes a sweep a sweep: the runner reads Knobs off the batch in flight."""
    knobs = Knobs(decision_interval=0.25, precision_threshold=8)
    sched = schedule(
        TrialBatch("baseline", (spec("one"),)),
        TrialBatch("swept", (spec("two"),), knobs),
    )
    d, sink = driver(sched)
    assert d.batch is not None
    assert d.batch.knobs == Knobs()
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    assert d.batch is not None
    assert d.batch.knobs == knobs
    assert outcomes(sink)[0].knobs == Knobs()


def test_the_knobs_in_force_are_written_into_the_outcome() -> None:
    """
    A record has to say what it was measured under. An outcome that named only its
    batch would need the schedule file, at the version it was run at, to be read.
    """
    knobs = Knobs(action_duration=0.5)
    d, sink = driver(schedule(TrialBatch("swept", (spec(),), knobs)))
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    assert outcomes(sink)[0].knobs == knobs


# --- Abandoning -------------------------------------------------------------------


def test_abandoning_closes_the_trial_in_flight_and_stops_the_run() -> None:
    """
    A calibration sitting usually ends by being stopped. The file should say so,
    rather than trailing off mid-cycle and reading like a crash.
    """
    sched = schedule(TrialBatch("b", (spec("one"), spec("two"))))
    d, sink = driver(sched)
    d.advance(at(0, 0), 0.0)
    d.advance(at(5, 0), 1.0)
    outcome = d.abandon(2.0)
    assert outcome is not None
    assert outcome.result == TrialResult.ABANDONED
    assert outcome.trial == "one"
    assert d.finished
    # The Trial that never started gets no outcome: it was never run, and one would
    # be a fabrication.
    assert [o.trial for o in outcomes(sink)] == ["one"]


def test_abandoning_a_finished_run_is_a_no_op() -> None:
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    before = len(sink)
    assert d.abandon(2.0) is None
    assert len(sink) == before


# --- Defect counters --------------------------------------------------------------


def test_an_overshoot_past_the_target_counts_as_an_oscillation() -> None:
    """
    Read off the *sign* of the displacement, not the distance: a loop that overshoots
    and comes back is converging badly, and an unsigned error cannot see the
    difference between that and a clean approach.
    """
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=100.0),))))
    d.advance(at(0, 0), 0.0)  # positioning done; measuring toward (10, 0)
    for position in [(5, 0), (14, 0), (6, 0), (13, 0)]:
        d.advance(at(*position), 1.0)
    d.advance(at(10, 0), 2.0)
    (outcome,) = outcomes(sink)
    assert outcome.oscillations == 3


def test_a_straight_approach_counts_no_oscillation() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=100.0),))))
    d.advance(at(0, 0), 0.0)
    for x in (2, 4, 6, 8):
        d.advance(at(x, 0), 1.0)
    d.advance(at(10, 0), 2.0)
    assert outcomes(sink)[0].oscillations == 0


def test_drawing_level_on_one_axis_is_not_an_oscillation() -> None:
    """
    A zero displacement component means "level with the target on this axis", which
    is not a direction. Treating it as one would count every arrival as an overshoot.
    """
    sched = schedule(
        TrialBatch("b", (spec(start=(0, 0), target=(10, 10), time_budget=100.0),))
    )
    d, sink = driver(sched)
    d.advance(at(0, 0), 0.0)
    for position in [(5, 5), (10, 7), (10, 9)]:
        d.advance(at(*position), 1.0)
    d.advance(at(10, 10), 2.0)
    assert outcomes(sink)[0].oscillations == 0


def test_cycles_without_progress_add_up_to_a_stuck_event() -> None:
    """
    The streak resets after each event, so a loop stuck three times as long as the
    threshold counts three times - one long stall and three short ones are not the
    same defect, and a single flag could not tell them apart.
    """
    policy = DefectPolicy(progress_epsilon=1.0, stall_cycles=3)
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=100.0),))), policy)
    d.advance(at(0, 0), 0.0)  # arrives at `start`; measuring begins
    for _ in range(7):
        d.advance(at(4, 0), 1.0)  # error pinned at 6.0: one baseline, then six stalls
    d.advance(at(10, 0), 2.0)
    outcome = outcomes(sink)[0]
    assert outcome.stuck_events == 2
    assert outcome.longest_stall == 3


def test_progress_below_the_epsilon_is_not_progress() -> None:
    """
    Minimap coordinates are a gross quantization of real-map pixels, so a crawl the
    detector cannot distinguish from noise is not progress. The same position stream
    is a stuck loop under one epsilon and a converging one under another, which is
    what makes the epsilon the thing being asserted here.
    """
    crawl = [(x, 0) for x in (1, 2, 3, 4)]
    sched = schedule(TrialBatch("b", (spec(target=(100, 0), time_budget=100.0),)))

    d, sink = driver(sched, DefectPolicy(progress_epsilon=5.0, stall_cycles=3))
    d.advance(at(0, 0), 0.0)
    for position in crawl:
        d.advance(at(*position), 1.0)
    d.advance(at(100, 0), 2.0)
    assert outcomes(sink)[0].stuck_events == 1

    d, sink = driver(sched, DefectPolicy(progress_epsilon=0.5, stall_cycles=3))
    d.advance(at(0, 0), 0.0)
    for position in crawl:
        d.advance(at(*position), 1.0)
    d.advance(at(100, 0), 2.0)
    assert outcomes(sink)[0].stuck_events == 0


def test_steady_progress_counts_no_stuck_event() -> None:
    policy = DefectPolicy(progress_epsilon=1.0, stall_cycles=3)
    sched = schedule(TrialBatch("b", (spec(target=(100, 0), time_budget=100.0),)))
    d, sink = driver(sched, policy)
    d.advance(at(0, 0), 0.0)
    for x in range(10, 100, 10):
        d.advance(at(x, 0), 1.0)
    d.advance(at(100, 0), 2.0)
    outcome = outcomes(sink)[0]
    assert outcome.stuck_events == 0
    assert outcome.longest_stall == 0


def test_defects_are_counted_over_the_measured_phase_only() -> None:
    """
    A character that thrashed on the way to `start` did not oscillate *in the Trial*.
    Counting it would attribute the setup's defects to the Knob being swept.
    """
    sched = schedule(TrialBatch("b", (spec(setup_budget=100.0, time_budget=100.0),)))
    d, sink = driver(sched)
    for position in [(-5, 0), (5, 0), (-5, 0), (5, 0)]:
        d.advance(at(*position), 0.0)
    d.advance(at(0, 0), 1.0)
    d.advance(at(10, 0), 2.0)
    assert outcomes(sink)[0].oscillations == 0


# --- Virtual positions (#397) -----------------------------------------------------


def test_an_unsure_position_judges_nothing_and_dispatches_nothing() -> None:
    """
    C-NOGUESS: an unsure read is no position. It cannot arrive, make progress or
    overshoot, and the runner holds rather than ship a plan from it.
    """
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=10.0),))))
    d.advance(at(0, 0), 0.0)
    verdict = d.advance(unsure(), 1.0)
    assert verdict.dispatch is False
    assert verdict.outcome is None
    record = cycles(sink)[-1]
    assert record.error is None
    assert record.position.position is None
    assert record.position.status == "unsure"


def test_an_unsure_trial_still_runs_out_of_budget_with_its_last_read_error() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=5.0),))))
    d.advance(at(0, 0), 0.0)
    d.advance(at(7, 0), 1.0)
    d.advance(unsure(), 3.0)
    d.advance(unsure(), 5.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.TIMEOUT
    assert outcome.final_error == 3.0
    assert outcome.unsure_cycles == 2


def test_a_trial_never_read_has_no_final_error() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(setup_budget=1.0),))))
    d.advance(unsure(), 0.0)
    d.advance(unsure(), 1.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.SETUP_FAILED
    assert outcome.final_error is None


def test_a_coarse_position_arrives_only_when_its_whole_pixel_is_inside() -> None:
    """
    A minimap-only position is the middle of a 16 px canvas pixel: on the target is
    not inside an 8 px tolerance, because the feet may be anywhere in that pixel.
    """
    tight = schedule(
        TrialBatch("b", (spec(target=(100, 0), tolerance=8.0, time_budget=10.0),))
    )
    d, _ = driver(tight)
    d.advance(at(0, 0), 0.0)
    assert d.advance(at(100, 0, PositionSource.COARSE), 1.0).outcome is None
    assert d.advance(at(100, 0), 2.0).outcome is not None

    loose = schedule(
        TrialBatch("b", (spec(target=(100, 0), tolerance=16.0, time_budget=10.0),))
    )
    d, _ = driver(loose)
    d.advance(at(0, 0), 0.0)
    verdict = d.advance(at(103, 0, PositionSource.COARSE), 1.0)
    assert 3 + COARSE_SLACK <= 16.0
    assert verdict.outcome is not None
    assert verdict.outcome.result == TrialResult.ARRIVED


def test_a_sample_is_recorded_and_judges_nothing() -> None:
    """
    A sample is a read while an Action is in flight: on the target or not, only a
    decision cycle closes a Trial. It names the Action in flight.
    """
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(at(5, 0), 1.0, correlation_id="cid-7")
    sample = d.sample(at(10, 0), 1.1)
    assert sample is not None
    assert sample.correlation_id == "cid-7"
    assert sample.position.position == (10.0, 0.0)
    assert sample.elapsed == pytest.approx(1.1)  # measuring began at 0.0
    assert outcomes(sink) == []
    assert d.trial is not None


def test_a_finished_schedule_takes_no_sample() -> None:
    d, sink = driver()
    d.advance(at(0, 0), 0.0)
    d.advance(at(10, 0), 1.0)
    before = len(sink)
    assert d.sample(at(10, 0), 2.0) is None
    assert len(sink) == before


def test_the_outcome_says_what_the_trial_measures() -> None:
    sched = schedule(TrialBatch("b", (spec(), spec("w", measures=Measure.WALK))))
    d, sink = driver(sched)
    for _ in range(2):
        d.advance(at(0, 0), 0.0)
        d.advance(at(10, 0), 1.0)
    assert [o.measures for o in outcomes(sink)] == [None, "walk"]


def test_the_default_policy_is_the_minimap_one_converted_to_virtual_px() -> None:
    """
    1 minimap px of progress is 16 virtual px, and level meant the same minimap
    pixel. Fused reads jittering a few px about a target level with the character
    are not overshoots.
    """
    policy = DefectPolicy()
    assert policy.progress_epsilon == 16.0
    assert policy.level_band == 8.0
    sched = schedule(
        TrialBatch("b", (spec(target=(0, 100), tolerance=1.0, time_budget=100.0),))
    )
    sink = ListSink()
    d = TrialDriver(sched, sink, defects=policy)
    d.advance(at(0, 0), 0.0)
    for x in (3, -4, 5, -3):
        d.advance(at(x, 50), 1.0)
    d.advance(at(0, 100), 2.0)
    assert outcomes(sink)[0].oscillations == 0


def test_a_given_header_opens_the_record() -> None:
    header = ScheduleHeader.now("sched", "Victoria Road: Ellinia", map_id=10002000)
    sink = ListSink()
    TrialDriver(schedule(), sink, header=header)
    assert sink[0] == header
