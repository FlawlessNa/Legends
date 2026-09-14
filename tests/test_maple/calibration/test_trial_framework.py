"""
The framework end to end, offline: a schedule walked over a real Corpus map.

This is issue #116's acceptance criterion - "the framework runs against
fakes/existing corpus maps and its record format round-trips" - and it is the only
check here that puts the whole chain together: a schedule, real pathfinding over a
real map's grid, real compilation of the Movement Plan, the driver's judgement, and
a JSONL file read back.

**What is fake is exactly one thing**: the character. `_walk` advances it along the
Path the movement layer just computed, a few nodes a cycle. Nothing offline can say
whether a real character follows its Path - that needs a client, and it is what
issue #120's campaign is for. Everything either side of that step is production
code, which is the point: a framework that only worked against a stub would be one
nobody could trust the first time it met a game.

Fixture maps rather than mapfiles: they are small, so a whole schedule runs in
milliseconds, and each one forces a movement type by construction, so the plans
compiled here are real plans rather than whatever a real map happened to yield.
"""

from pathlib import Path

import pytest

from botting.controller import InputState
from maple.calibration.driver import TrialDriver
from maple.calibration.records import (
    CycleRecord,
    JsonlRecordWriter,
    ListSink,
    Phase,
    Record,
    RecordSink,
    ScheduleHeader,
    TrialOutcome,
    TrialResult,
    read_records,
    summarize_plan,
    summarize_sequence,
)
from maple.calibration.specs import Knobs, TrialBatch, TrialSchedule, TrialSpec
from maple.model.mechanics.movement_mechanics_v2 import MovementHandler
from tests.test_maple.movement_lab import corpus

#: How many Path nodes the fake character covers per cycle. Not a measured constant
#: and not pretending to be one - it only has to be more than zero, so that a Path
#: gets walked and the loop converges.
_NODES_PER_CYCLE = 3

#: The clock, in seconds per cycle. Only differences matter to the driver.
_CYCLE_SECONDS = 0.5

WALK = next(e for e in corpus.FIXTURE_MAPS if e.name == "walk_corridor")
LEDGE = next(e for e in corpus.FIXTURE_MAPS if e.name == "jump_ledge")
PERCH = next(e for e in corpus.FIXTURE_MAPS if e.name == "narrow_perch")


# --- Running a schedule offline ---------------------------------------------------


def _pair(entry: corpus.CorpusMap) -> tuple[tuple[int, int], tuple[int, int]]:
    """The map's longest reachable pair from the frozen sample - the busiest Path."""
    reachable = [record for record in corpus.plans(entry) if record.path]
    assert reachable, f"{entry.name} has no reachable pair in its frozen sample"
    longest = max(reachable, key=lambda record: len(record.path))
    return longest.pair.start, longest.pair.end


def _run(
    entry: corpus.CorpusMap,
    driver: TrialDriver,
    *,
    max_cycles: int = 400,
    compile_plans: bool = False,
) -> TrialDriver:
    """
    Walk a whole schedule, cycle by cycle, in `TrialRunner._decide`'s order.

    That order is the point: read the position, path to the driver's target, hand
    the plan over, dispatch only if the driver says to. A helper that decided in a
    different order would be checking a loop nobody runs.

    `max_cycles` is a stop, not a budget - a Trial ends on its own time budget, and
    this only keeps a framework defect from hanging the suite.
    """
    grid = corpus.grid(entry)
    move = corpus.handler(entry)
    position = driver.schedule.trials[0][1].start
    now = 0.0

    for _ in range(max_cycles):
        target = driver.target
        if target is None:
            break
        path = move.compute_path(position, target, grid)
        plan = move.path_into_movements(path, grid) if path else ()
        sequence = (
            summarize_sequence(
                move.movements_into_action(
                    plan, grid, total_duration=1.0, initial_state=InputState()
                )
            )
            if compile_plans and plan
            else None
        )
        verdict = driver.advance(
            position,
            now,
            plan=summarize_plan(plan),
            correlation_id=f"cycle-{len(path)}",
            sequence=sequence,
        )
        now += _CYCLE_SECONDS
        if verdict.dispatch:
            position = _walk(path, position)
    return driver


def _walk(path: tuple, position: tuple[int, int]) -> tuple[int, int]:
    """
    The one fake: the character follows its Path.

    A real one may not - it overshoots, lands short, or falls off - and no offline
    check can say which. What this stands in for is only "the Action moved the
    character somewhere along the plan", which is what the loop needs in order to
    have another cycle to record.
    """
    if not path:
        return position
    node = path[min(_NODES_PER_CYCLE, len(path) - 1)]
    return int(node.x), int(node.y)


def _schedule(entry: corpus.CorpusMap, **spec_kwargs: object) -> TrialSchedule:
    start, target = _pair(entry)
    trial = TrialSpec(
        name="reachable-pair",
        start=start,
        target=target,
        tolerance=2.0,
        time_budget=120.0,
        **spec_kwargs,  # type: ignore[arg-type]
    )
    return TrialSchedule(f"{entry.name}-lab", entry.name, (TrialBatch("b", (trial,)),))


# --- The acceptance check ---------------------------------------------------------


@pytest.mark.parametrize("entry", [WALK, LEDGE], ids=lambda e: e.name)
def test_a_schedule_runs_to_arrival_over_a_corpus_map(
    entry: corpus.CorpusMap, held_movement_keys: object
) -> None:
    """
    The whole chain: real grid, real Path, real Movement Plan, real compilation,
    and the driver's verdict on every cycle of it.
    """
    sink = ListSink()
    driver = TrialDriver(_schedule(entry), sink)
    _run(entry, driver, compile_plans=True)

    assert driver.finished
    outcomes = [r for r in sink if isinstance(r, TrialOutcome)]
    assert [o.result for o in outcomes] == [TrialResult.ARRIVED]
    assert outcomes[0].final_error <= outcomes[0].tolerance


@pytest.mark.parametrize("entry", [WALK, LEDGE], ids=lambda e: e.name)
def test_the_cycles_carry_the_movement_plan_that_was_chosen(
    entry: corpus.CorpusMap, held_movement_keys: object
) -> None:
    """
    A record whose plan was empty would be a record of a loop that decided nothing.
    Every dispatched cycle names the components it shipped, ending in the sentinel
    every Movement Plan ends with.
    """
    sink = ListSink()
    _run(entry, TrialDriver(_schedule(entry), sink), compile_plans=True)

    dispatched = [r for r in sink if isinstance(r, CycleRecord) and r.dispatched]
    assert dispatched
    for record in dispatched:
        assert record.plan
        assert record.plan[-1].movement_type == "END_OF_MOVEMENT"
        assert record.sequence is not None
        assert record.sequence.step_count > 0


def test_the_error_shrinks_as_the_loop_converges(held_movement_keys: object) -> None:
    """
    The thing a Trial exists to measure. Not a tolerance check - that is arrival -
    but the shape of the approach: a loop re-planning from the detected position
    every cycle should be getting closer, not circling.
    """
    sink = ListSink()
    _run(WALK, TrialDriver(_schedule(WALK), sink))

    measured = [
        r for r in sink if isinstance(r, CycleRecord) and r.phase == Phase.MEASURING
    ]
    assert len(measured) > 2
    assert measured[-1].error < measured[0].error


def test_a_trial_whose_budget_runs_out_is_recorded_as_a_timeout(
    held_movement_keys: object,
) -> None:
    """
    The failure the campaign is looking for. A budget too short to reach the target
    ends the Trial, and the record says how far off it was rather than trailing off.
    """
    start, target = _pair(WALK)
    schedule = TrialSchedule(
        "tight",
        WALK.name,
        (
            TrialBatch(
                "b",
                (TrialSpec("too-tight", start, target, 2.0, 1.0, setup_budget=120.0),),
            ),
        ),
    )
    sink = ListSink()
    _run(WALK, TrialDriver(schedule, sink))

    (outcome,) = [r for r in sink if isinstance(r, TrialOutcome)]
    assert outcome.result == TrialResult.TIMEOUT
    assert outcome.final_error > outcome.tolerance


# --- Round-tripping a real run ----------------------------------------------------


def test_a_recorded_run_reads_back_exactly(
    tmp_path: Path, held_movement_keys: object
) -> None:
    """
    The other half of the acceptance criterion, over a file a real run produced
    rather than over hand-built records: a record is read back on a machine with no
    client and no way to repeat the sitting, so anything lost on the way through is
    lost for good.
    """
    schedule = _schedule(LEDGE)
    memory = ListSink()
    path = tmp_path / "run.jsonl"

    with JsonlRecordWriter(path) as writer:
        both = _TeeSink(writer, memory)
        _run(LEDGE, TrialDriver(schedule, both), compile_plans=True)

    read_back = read_records(path)
    assert read_back == list(memory)
    assert isinstance(read_back[0], ScheduleHeader)
    assert read_back[0].map_name == LEDGE.name
    assert isinstance(read_back[-1], TrialOutcome)


class _TeeSink:
    """Writes to a file and keeps a copy, so the two can be compared afterwards."""

    def __init__(self, *sinks: RecordSink) -> None:
        self._sinks = sinks

    def write(self, record: Record) -> None:
        for sink in self._sinks:
            sink.write(record)

    def close(self) -> None:
        """The `with` block owns the file writer, so closing is not this sink's to
        do - but a sink has to have the method."""


# --- The precision-movement Knob --------------------------------------------------


def test_the_precision_threshold_knob_changes_which_landings_are_narrow() -> None:
    """
    The `precision_threshold` Knob has to reach the Movement Plan, or a batch that
    sweeps it measures the default three times.

    It is a `MovementHandler` attribute rather than the module constant so that
    sweeping it is per-run rather than process-wide - and it shapes the plan here, in
    the Engine. `compile_movements` reads the component's `narrow` flag and never the
    threshold, so the send path is untouched by the sweep.
    """
    grid = corpus.grid(PERCH)
    minimap = corpus.minimap(PERCH)
    start, target = _pair(PERCH)

    def narrow_count(threshold: float) -> int:
        handler = MovementHandler(
            corpus.LAB_HANDLE,
            minimap,
            corpus.LAB_IGN,
            narrow_platform_threshold=threshold,
        )
        path = handler.compute_path(start, target, grid)
        plan = handler.path_into_movements(path, grid)
        return sum(1 for component in plan if component.narrow)

    assert narrow_count(0) == 0
    assert narrow_count(Knobs().precision_threshold or 5) > 0


def test_the_default_threshold_is_what_production_gets() -> None:
    """
    An unswept run must compile the same plans as `Rotation` does. A handler built
    without the Knob is the production one.
    """
    default = MovementHandler(corpus.LAB_HANDLE, corpus.minimap(PERCH), corpus.LAB_IGN)
    grid = corpus.grid(PERCH)
    start, target = _pair(PERCH)
    path = default.compute_path(start, target, grid)

    assert default.path_into_movements(path, grid) == corpus.handler(
        PERCH
    ).path_into_movements(path, grid)
