"""
Movement calibration: the closed-loop Trial framework.

A **Trial** is one closed-loop A->B run under the real Session machinery, judged on
arrival reliability first and time-to-arrival second (`CONTEXT.md` -> Movement
calibration). This package holds the three pieces a Trial needs and nothing that
needs a game client:

* `specs` - the checked-in schedule: Trials, batches, and the **Knob** overrides a
  batch sweeps.
* `records` - the per-machine JSONL a run leaves behind, and how to read it back.
* `driver` - the loop's judgement, fed virtual positions and a clock from outside.
* `analysis` - the physics schedule's records turned into Calibration constants,
  offline (`python -m maple.calibration.analysis <record>`).

The bot around them is `maple.bots.CalibrationBot`, whose single DecisionMaker is
`maple.decision_makers.TrialRunner`. It ships Movement Plans through the production
decide -> compile -> send path rather than a loop of its own, because a bespoke
runner would measure a copy of the system instead of the system.
"""

from .driver import DefectPolicy, TrialDriver, Verdict
from .records import (
    CycleRecord,
    JsonlRecordWriter,
    ListSink,
    MovementSummary,
    Phase,
    PositionRecord,
    RecordSink,
    SampleRecord,
    ScheduleHeader,
    SequenceSummary,
    TrialOutcome,
    TrialResult,
    default_record_path,
    read_records,
    summarize_plan,
    summarize_sequence,
)
from .specs import (
    KNOB_NAMES,
    Knobs,
    Measure,
    TrialBatch,
    TrialSchedule,
    TrialSpec,
    TrialSpecError,
    available,
    load_schedule,
    render_schedule,
    schedule_map_id,
)

__all__ = [
    "KNOB_NAMES",
    "CycleRecord",
    "DefectPolicy",
    "JsonlRecordWriter",
    "Knobs",
    "ListSink",
    "Measure",
    "MovementSummary",
    "Phase",
    "PositionRecord",
    "RecordSink",
    "SampleRecord",
    "ScheduleHeader",
    "SequenceSummary",
    "TrialBatch",
    "TrialDriver",
    "TrialOutcome",
    "TrialResult",
    "TrialSchedule",
    "TrialSpec",
    "TrialSpecError",
    "Verdict",
    "available",
    "default_record_path",
    "load_schedule",
    "read_records",
    "render_schedule",
    "schedule_map_id",
    "summarize_plan",
    "summarize_sequence",
]
