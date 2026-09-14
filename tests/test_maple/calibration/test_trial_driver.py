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

from maple.calibration.driver import DefectPolicy, TrialDriver
from maple.calibration.records import (
    CycleRecord,
    ListSink,
    Phase,
    ScheduleHeader,
    TrialOutcome,
    TrialResult,
)
from maple.calibration.specs import Knobs, TrialBatch, TrialSchedule, TrialSpec


def spec(
    name: str = "t",
    start: tuple[int, int] = (0, 0),
    target: tuple[int, int] = (10, 0),
    tolerance: float = 1.0,
    time_budget: float = 10.0,
    setup_budget: float | None = None,
) -> TrialSpec:
    return TrialSpec(name, start, target, tolerance, time_budget, setup_budget)


def schedule(*batches: TrialBatch) -> TrialSchedule:
    return TrialSchedule(
        "sched", "fixture-map", batches or (TrialBatch("b", (spec(),)),)
    )


def driver(
    sched: TrialSchedule | None = None, policy: DefectPolicy | None = None
) -> tuple[TrialDriver, ListSink]:
    sink = ListSink()
    return TrialDriver(sched or schedule(), sink, defects=policy), sink


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
    assert header.map_name == "fixture-map"


# --- Positioning ------------------------------------------------------------------


def test_a_trial_aims_at_its_start_before_it_aims_at_its_target() -> None:
    """
    A Trial that began somewhere other than its `start` measured a different run.
    The walk there is a phase of the Trial, not a precondition someone remembered.
    """
    d, _ = driver()
    assert d.phase is Phase.POSITIONING
    assert d.target == (0, 0)

    d.advance((5, 0), 0.0)
    assert d.phase is Phase.POSITIONING

    d.advance((0, 0), 1.0)
    assert d.phase is Phase.MEASURING
    assert d.target == (10, 0)


def test_the_measured_clock_starts_when_the_character_reaches_the_start() -> None:
    """Time spent walking to `start` is not time-to-arrival."""
    d, sink = driver()
    d.advance((9, 0), 0.0)
    d.advance((0, 0), 30.0)  # arrived at `start`, 30s in
    d.advance((10, 0), 32.0)  # arrived at `target`, 2s later
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.ARRIVED
    assert outcome.time_to_arrival == 2.0


def test_the_positioning_phase_has_its_own_budget() -> None:
    d, sink = driver(
        schedule(TrialBatch("b", (spec(time_budget=10.0, setup_budget=3.0),)))
    )
    d.advance((9, 0), 0.0)
    d.advance((9, 0), 3.0)
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.SETUP_FAILED


def test_a_trial_that_never_reached_its_start_reports_no_measurement() -> None:
    """
    `SETUP_FAILED` is not a slow arrival. A Trial whose character never got to its
    start has no time-to-arrival, and reporting one would fabricate a measurement.
    """
    d, sink = driver(schedule(TrialBatch("b", (spec(setup_budget=1.0),))))
    d.advance((9, 0), 0.0)
    d.advance((9, 0), 1.0)
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
    d.advance((9, 0), 0.0)
    d.advance((0, 0), 1.0)
    d.advance((10, 0), 2.0)
    phases = [c.phase for c in cycles(sink)]
    assert phases == [Phase.POSITIONING, Phase.POSITIONING, Phase.MEASURING]


def test_a_character_already_at_the_start_measures_from_the_first_cycle() -> None:
    d, sink = driver()
    d.advance((0, 0), 0.0)
    assert d.phase is Phase.MEASURING
    d.advance((10, 0), 4.0)
    (outcome,) = outcomes(sink)
    assert outcome.time_to_arrival == 4.0


# --- Arrival and budget -----------------------------------------------------------


def test_arrival_is_inside_the_tolerance_not_exactly_on_the_target() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(tolerance=2.0),))))
    d.advance((0, 0), 0.0)
    d.advance((9, 1), 1.0)  # distance sqrt(2) < 2.0
    (outcome,) = outcomes(sink)
    assert outcome.result == TrialResult.ARRIVED
    assert outcome.final_error == pytest.approx(2**0.5)


def test_running_out_of_budget_ends_the_trial_and_records_how_far_off_it_was() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=5.0),))))
    d.advance((0, 0), 0.0)
    d.advance((7, 0), 5.0)
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
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
    last = cycles(sink)[-1]
    assert last.position == (10, 0)
    assert last.error == 0.0
    assert last.dispatched is False


def test_the_cycle_count_covers_the_measured_phase_only() -> None:
    """
    Two Trials are compared on cycles-to-arrival. Folding in however many cycles the
    walk to `start` happened to need would make that comparison meaningless.
    """
    d, sink = driver()
    for t in range(4):
        d.advance((9, 0), float(t))  # four positioning cycles
    d.advance((0, 0), 4.0)  # the fifth, which arrives at `start`
    d.advance((5, 0), 5.0)
    d.advance((10, 0), 6.0)
    (outcome,) = outcomes(sink)
    assert outcome.cycles == 2
    assert len(cycles(sink)) == 7


# --- What the runner is told ------------------------------------------------------


def test_a_cycle_still_short_of_the_target_asks_for_a_dispatch() -> None:
    d, _ = driver()
    d.advance((0, 0), 0.0)
    verdict = d.advance((5, 0), 1.0)
    assert verdict.dispatch is True
    assert verdict.target == (10, 0)
    assert verdict.outcome is None


def test_an_arriving_cycle_asks_for_no_dispatch() -> None:
    """Sending a plan built for a target already reached is how a loop oscillates."""
    d, _ = driver()
    d.advance((0, 0), 0.0)
    verdict = d.advance((10, 0), 1.0)
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
    d.advance((0, 0), 0.0)
    d.advance(
        (5, 0),
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
        d.advance((0, 0), 0.0)
        d.advance((10, 0), 1.0)
    assert [o.trial for o in outcomes(sink)] == ["one", "two", "three"]
    assert [o.batch for o in outcomes(sink)] == ["first", "first", "second"]
    assert d.finished
    assert d.target is None


def test_advancing_a_finished_schedule_records_nothing() -> None:
    d, sink = driver()
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
    before = len(sink)
    verdict = d.advance((10, 0), 2.0)
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
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
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
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
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
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
    assert outcomes(sink)[0].knobs == knobs


# --- Abandoning -------------------------------------------------------------------


def test_abandoning_closes_the_trial_in_flight_and_stops_the_run() -> None:
    """
    A calibration sitting usually ends by being stopped. The file should say so,
    rather than trailing off mid-cycle and reading like a crash.
    """
    sched = schedule(TrialBatch("b", (spec("one"), spec("two"))))
    d, sink = driver(sched)
    d.advance((0, 0), 0.0)
    d.advance((5, 0), 1.0)
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
    d.advance((0, 0), 0.0)
    d.advance((10, 0), 1.0)
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
    d.advance((0, 0), 0.0)  # positioning done; measuring toward (10, 0)
    for position in [(5, 0), (14, 0), (6, 0), (13, 0)]:
        d.advance(position, 1.0)
    d.advance((10, 0), 2.0)
    (outcome,) = outcomes(sink)
    assert outcome.oscillations == 3


def test_a_straight_approach_counts_no_oscillation() -> None:
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=100.0),))))
    d.advance((0, 0), 0.0)
    for x in (2, 4, 6, 8):
        d.advance((x, 0), 1.0)
    d.advance((10, 0), 2.0)
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
    d.advance((0, 0), 0.0)
    for position in [(5, 5), (10, 7), (10, 9)]:
        d.advance(position, 1.0)
    d.advance((10, 10), 2.0)
    assert outcomes(sink)[0].oscillations == 0


def test_cycles_without_progress_add_up_to_a_stuck_event() -> None:
    """
    The streak resets after each event, so a loop stuck three times as long as the
    threshold counts three times - one long stall and three short ones are not the
    same defect, and a single flag could not tell them apart.
    """
    policy = DefectPolicy(progress_epsilon=1.0, stall_cycles=3)
    d, sink = driver(schedule(TrialBatch("b", (spec(time_budget=100.0),))), policy)
    d.advance((0, 0), 0.0)  # arrives at `start`; measuring begins
    for _ in range(7):
        d.advance((4, 0), 1.0)  # error pinned at 6.0: one baseline, then six stalls
    d.advance((10, 0), 2.0)
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
    d.advance((0, 0), 0.0)
    for position in crawl:
        d.advance(position, 1.0)
    d.advance((100, 0), 2.0)
    assert outcomes(sink)[0].stuck_events == 1

    d, sink = driver(sched, DefectPolicy(progress_epsilon=0.5, stall_cycles=3))
    d.advance((0, 0), 0.0)
    for position in crawl:
        d.advance(position, 1.0)
    d.advance((100, 0), 2.0)
    assert outcomes(sink)[0].stuck_events == 0


def test_steady_progress_counts_no_stuck_event() -> None:
    policy = DefectPolicy(progress_epsilon=1.0, stall_cycles=3)
    sched = schedule(TrialBatch("b", (spec(target=(100, 0), time_budget=100.0),)))
    d, sink = driver(sched, policy)
    d.advance((0, 0), 0.0)
    for x in range(10, 100, 10):
        d.advance((x, 0), 1.0)
    d.advance((100, 0), 2.0)
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
        d.advance(position, 0.0)
    d.advance((0, 0), 1.0)
    d.advance((10, 0), 2.0)
    assert outcomes(sink)[0].oscillations == 0
