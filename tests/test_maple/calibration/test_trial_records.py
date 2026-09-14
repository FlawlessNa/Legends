"""
Trial records: that the JSONL format round-trips, exactly.

This is the acceptance criterion issue #116 states, and it is not a formality. A
Trial record is written once, on a machine with a game client attached, and read
back later by an analyzer on a machine without one. If a field is dropped or coerced
on the way through, the run cannot be repeated to find out what it said - the client,
the character and the sitting are gone.

So the checks here are equality checks on whole objects, never on a field or two: a
field added later without a `from_json` for it fails this file rather than silently
vanishing from every record written afterwards.
"""

import json
from pathlib import Path

import pytest

from botting.controller import KeyboardInputWrapper
from maple.calibration.records import (
    CycleRecord,
    JsonlRecordWriter,
    ListSink,
    MovementSummary,
    Phase,
    Record,
    ScheduleHeader,
    SequenceSummary,
    TrialOutcome,
    TrialResult,
    default_record_path,
    read_records,
    summarize_plan,
    summarize_sequence,
)
from maple.calibration.specs import Knobs
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)

HEADER = ScheduleHeader("example", "GhostShip1", "2026-01-01T00:00:00+00:00", "host")

CYCLE = CycleRecord(
    schedule="example",
    batch="baseline",
    trial="long-run",
    phase=str(Phase.MEASURING),
    cycle=3,
    elapsed=1.25,
    wall_clock="2026-01-01T00:00:01+00:00",
    position=(15, 42),
    target=(109, 42),
    error=94.0,
    dispatched=True,
    correlation_id="6f1f7d4e-0000-4000-8000-000000000000",
    plan=(
        MovementSummary("WALK_RIGHT", 5, False, False),
        MovementSummary("JUMP", 1, True, False),
    ),
    sequence=SequenceSummary(4, 0.75, ("right", "space"), ("right",)),
)

OUTCOME = TrialOutcome(
    schedule="example",
    batch="baseline",
    trial="long-run",
    knobs=Knobs(decision_interval=0.25, precision_threshold=8),
    start=(15, 42),
    target=(109, 42),
    tolerance=2.0,
    time_budget=20.0,
    result=str(TrialResult.ARRIVED),
    final_error=1.4,
    time_to_arrival=8.5,
    duration=8.5,
    cycles=17,
    oscillations=2,
    stuck_events=1,
    longest_stall=6,
    started_at="2026-01-01T00:00:00+00:00",
)


# --- Round-tripping ---------------------------------------------------------------


@pytest.mark.parametrize(
    "record", [HEADER, CYCLE, OUTCOME], ids=["header", "cycle", "outcome"]
)
def test_a_record_survives_json_unchanged(record: Record) -> None:
    assert type(record).from_json(json.loads(json.dumps(record.to_json()))) == record


def test_a_whole_file_reads_back_as_what_was_written(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    with JsonlRecordWriter(path) as writer:
        for record in (HEADER, CYCLE, OUTCOME):
            writer.write(record)
    assert read_records(path) == [HEADER, CYCLE, OUTCOME]


def test_a_cycle_with_no_compiled_sequence_round_trips_as_none(tmp_path: Path) -> None:
    """
    The live path's shape: compilation happens in Main Process at dispatch, so the
    Engine that records the cycle has no Input Sequence to summarize and the
    Correlation ID is what an analyzer joins on instead.
    """
    bare = CycleRecord(
        schedule="example",
        batch="baseline",
        trial="long-run",
        phase=str(Phase.POSITIONING),
        cycle=1,
        elapsed=0.0,
        wall_clock="2026-01-01T00:00:00+00:00",
        position=(15, 42),
        target=(15, 42),
        error=0.0,
        dispatched=False,
    )
    path = tmp_path / "bare.jsonl"
    with JsonlRecordWriter(path) as writer:
        writer.write(bare)
    (read_back,) = read_records(path)
    assert isinstance(read_back, CycleRecord)
    assert read_back == bare
    assert read_back.sequence is None
    assert read_back.correlation_id is None


def test_records_written_across_two_sittings_append(tmp_path: Path) -> None:
    """A writer opens for append: reopening the same path never truncates a record."""
    path = tmp_path / "run.jsonl"
    with JsonlRecordWriter(path) as writer:
        writer.write(HEADER)
    with JsonlRecordWriter(path) as writer:
        writer.write(CYCLE)
    assert read_records(path) == [HEADER, CYCLE]


def test_every_line_is_flushed_before_the_writer_is_closed(tmp_path: Path) -> None:
    """
    A calibration sitting usually ends by killing the Session, so a record only
    readable after a clean close would routinely be an empty file.
    """
    path = tmp_path / "run.jsonl"
    writer = JsonlRecordWriter(path)
    writer.write(HEADER)
    writer.write(CYCLE)
    assert read_records(path) == [HEADER, CYCLE]
    writer.close()


def test_an_unknown_record_kind_raises_rather_than_being_skipped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "future.jsonl"
    path.write_text(json.dumps({"kind": "divergence"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown record kind"):
        read_records(path)


def test_a_blank_line_is_not_a_record(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    path.write_text(json.dumps(HEADER.to_json()) + "\n\n", encoding="utf-8")
    assert read_records(path) == [HEADER]


def test_the_writer_creates_the_records_directory(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "run.jsonl"
    with JsonlRecordWriter(path) as writer:
        writer.write(HEADER)
    assert path.exists()


def test_the_default_record_path_sorts_chronologically(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    earlier = default_record_path("example", tmp_path, datetime(2026, 1, 1, tzinfo=UTC))
    later = default_record_path("example", tmp_path, datetime(2026, 2, 1, tzinfo=UTC))
    assert earlier.name < later.name
    assert later.suffix == ".jsonl"
    assert "example" in later.name


# --- Summaries --------------------------------------------------------------------


def test_a_movement_plan_is_summarized_by_type_name() -> None:
    """
    Names, not `IntEnum` values: a record read a year later must not depend on
    `MovementTypes` still numbering its members the same way.
    """
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 5),
        _MovementComponent(MovementTypes.JUMP_LEFT, 1, narrow=True),
        _MovementComponent(
            MovementTypes.TELEPORT_RIGHT, 1, narrow=True, edge_departure=True
        ),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
    )
    assert summarize_plan(plan) == (
        MovementSummary("WALK_RIGHT", 5, False, False),
        MovementSummary("JUMP_LEFT", 1, True, False),
        MovementSummary("TELEPORT_RIGHT", 1, True, True),
        MovementSummary("END_OF_MOVEMENT", 1, False, False),
    )


def test_an_empty_plan_summarizes_to_nothing() -> None:
    assert summarize_plan(None) == ()
    assert summarize_plan(()) == ()


def test_a_compiled_sequence_summary_flattens_simultaneous_steps(
    held_movement_keys: object,
) -> None:
    """
    A Step's key may be a list (keys pressed together). The summary is the order the
    sequence touches keys in, which is what an oscillation looks like in a record, so
    a grouped Step contributes its keys rather than a nested list.
    """
    sequence = KeyboardInputWrapper(
        handle=0,
        keys=["right", ["left", "up"]],
        events=["keydown", ["keydown", "keydown"]],
        delays=[0.1, 0.2],
        forced_key_releases=["right"],
    )
    summary = summarize_sequence(sequence)
    assert summary is not None
    assert summary.keys == ("right", "left", "up")
    assert summary.step_count == 2
    # The sequence's own duration, verbatim. Not a re-derivation from the delays:
    # `KeyboardInputWrapper.duration` folds in the per-Step `OVERHEAD` measured at
    # import, and a summary that recomputed it would disagree with the sequence sent.
    assert summary.duration == sequence.duration
    assert summary.forced_releases == ("right",)


def test_nothing_compiled_summarizes_to_none() -> None:
    """`compile_movements` returns None for a plan with nothing in it."""
    assert summarize_sequence(None) is None


# --- Sinks ------------------------------------------------------------------------


def test_the_list_sink_keeps_records_in_order() -> None:
    sink = ListSink()
    sink.write(HEADER)
    sink.write(CYCLE)
    assert list(sink) == [HEADER, CYCLE]
