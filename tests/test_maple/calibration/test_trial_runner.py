"""
The `TrialRunner`: that the thin half is wired the way it claims to be.

Two things about this DecisionMaker cannot be read off the driver's checks, and both
are the kind a live run would only reveal by producing a misleading record:

1. **It ships through the production path.** The Action it sends carries
   `controller.compile_and_send` and a Movement Plan, so a Trial measures
   dispatch-time compilation, the Held-Keys Ledger and the focus lock (ADR 0002). A
   runner that compiled for itself would measure a copy of the system.
2. **Knobs are applied per batch, off the defaults.** A batch that sweeps a Knob must
   not leave it swept for the next batch that does not, or a three-batch sweep
   silently measures the swept value twice.

`_create_minimap_attributes` needs a game client, so the runner is built field by
field here rather than through `__init__`. That is the seam working as intended -
everything skipped is screenshot plumbing, and everything exercised below is the
runner's own logic - but it does mean this module says nothing about whether the
DecisionMaker starts up against a real client. It cannot; nothing offline can.
"""

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, ClassVar, Self, cast

import pytest

from botting.core import ActionRequest
from botting.core.bot_data import BotData
from botting.screen import Reading
from maple.calibration.driver import TrialDriver
from maple.calibration.records import (
    CycleRecord,
    ListSink,
    SampleRecord,
    TrialOutcome,
)
from maple.calibration.specs import (
    Knobs,
    TrialBatch,
    TrialSchedule,
    TrialSpec,
    TrialSpecError,
)
from maple.decision_makers.trial_runner import TrialRunner
from maple.model.mechanics.movement_mechanics_v2 import _NARROW_PLATFORM_THRESHOLD
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab import corpus

ENTRY = next(e for e in corpus.FIXTURE_MAPS if e.name == "walk_corridor")

#: A Trial's start and target, the feet in virtual px: both on `walk_corridor`'s
#: floor, a walk apart.
START = (16, 0)
TARGET = (288, 0)


class _Pipe:
    """Stands in for the Engine's pipe: keeps what was sent instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[ActionRequest] = []

    def send(self, request: ActionRequest) -> None:
        self.sent.append(request)


class _Character:
    """A character with no skills - `walk_corridor` needs none, and Teleport would
    change which graph the Paths are planned on."""

    skills: ClassVar[dict[str, object]] = {}


@dataclass
class _Harness:
    """
    A `TrialRunner` and the three things a check has to reach into it: the positions
    it reads, the pipe it sends on, and the records it writes.

    Kept beside the runner rather than read back off it, because the runner's own
    `pipe` and `_writer` are typed for the live path - a `Connection` and a file
    writer - and the stand-ins are neither.
    """

    runner: TrialRunner
    positions: list[tuple[float, float]]
    pipe: _Pipe
    writer: ListSink


@pytest.fixture
def harness() -> _Harness:
    """
    A `TrialRunner` assembled without its client-facing half.

    `__init__` is skipped because `_create_minimap_attributes` reads a game window.
    What is built here is everything downstream of that: a real `BotData` over a real
    Corpus map, so `_create_pathing_attributes` builds a real `MovementHandler` and
    `path`/`movements` compute real Paths. `current_position` hands out the
    virtual positions a check queues, as fused reads; the Trial judges them, and the
    Path is planned from them.
    """
    entry = ENTRY
    start, target = START, TARGET
    positions: list[tuple[float, float]] = []
    pipe = _Pipe()
    writer = ListSink()
    world_map = corpus.world_map(entry)

    data = BotData("Lab")
    data.set_static("handle", corpus.LAB_HANDLE)
    data.set_static("world_map", world_map)
    data.set_static("game_physics", corpus.LAB_PHYSICS_VALUES)
    data.set_static("speed_multiplier", 1.0)
    data.set_static("jump_multiplier", 1.0)
    data.set_static("character", _Character())

    def virtual() -> Reading[VirtualPosition]:
        x, y = positions.pop(0) if positions else target
        return Reading.read(VirtualPosition(x, y, PositionSource.FUSED), 0.0)

    # No threshold: read once per cycle, by the runner's `update_attribute`, as
    # production's 0.1 s threshold does at its decision interval.
    data.create_attribute(
        "current_position", virtual, initial_value=_read((float(start[0]), 0.0))
    )

    # Assembled through a deliberately untyped handle: every field below is a
    # stand-in for something only a live Session provides.
    self: Any = object.__new__(TrialRunner)
    self.data = data
    self.pipe = pipe
    self.lock = threading.Lock()
    self.correlation_id = "cid-0"
    self.schedule = _schedule(entry)
    self._writer = writer
    self._last_target = start
    self._batch_teleport = True
    self._driver = TrialDriver(self.schedule, writer)
    self._applied_batch = None
    self._finished = False
    self._apply_knobs()
    # The graph builds in a worker thread from setup on (#430), and planning holds
    # until it is there; a Session's first cycles would. Waited for here, so the
    # cycles below plan.
    data.movement_handler.graph(self._physics())
    # `path` refreshes on a 0.1s threshold, which production's decision interval
    # spaces its cycles out by. These cycles run in microseconds, so without this the
    # second one would re-read the first one's Path - a test-clock artefact, not
    # behaviour worth pinning. Not `None` or `0`: `ManagedAttribute.get` reads a
    # falsy threshold as "never refresh".
    data.reconfigure_attribute("path", threshold=1e-9)
    return _Harness(cast(TrialRunner, self), positions, pipe, writer)


def _schedule(entry: corpus.CorpusMap) -> TrialSchedule:
    trial = TrialSpec("reachable-pair", START, TARGET, 2.0, 60.0)
    return TrialSchedule(
        "runner-lab",
        entry.name,
        (
            TrialBatch("baseline", (trial,)),
            TrialBatch(
                "swept",
                (trial,),
                Knobs(
                    decision_interval=0.5, action_duration=0.25, precision_threshold=9
                ),
            ),
            TrialBatch("back-to-default", (trial,)),
        ),
    )


# --- The production path ----------------------------------------------------------


def test_the_action_it_sends_compiles_at_dispatch(harness: _Harness) -> None:
    """
    The Action carries `compile_and_send` and a compiler over the Movement Plan -
    never a compiled Input Sequence (ADR 0002). This is what makes a Trial a
    measurement of the system rather than of a copy of it.
    """
    from botting import controller

    request = harness.runner._request()
    assert isinstance(request, ActionRequest)
    assert request.procedure is controller.compile_and_send
    handle, compiler = request.args
    assert handle == corpus.LAB_HANDLE
    assert compiler.func is _compile_movements()
    assert "movements" in compiler.keywords


def test_a_decision_cycle_ships_a_plan_and_records_it(harness: _Harness) -> None:
    """
    Two cycles, because the first one is the Trial reaching its `start`: it plans
    toward `start`, finds itself there, and dispatches nothing. The second is the
    first measured cycle, and that is the one that ships a plan.
    """
    start = START
    harness.positions.extend([start, start])

    asyncio.run(harness.runner._decide())  # positioning completes
    asyncio.run(harness.runner._decide())  # first measured cycle

    (request,) = harness.pipe.sent
    assert request.correlation_id == "cid-0"
    recorded = [r for r in harness.writer if isinstance(r, CycleRecord)]
    assert recorded[-1].dispatched is True
    assert recorded[-1].plan
    assert recorded[-1].correlation_id == "cid-0"


def test_the_lock_holds_a_cycle_open_until_the_action_is_dispatched(
    harness: _Harness,
) -> None:
    """
    One Action in flight at a time, as `Rotation` does it. A runner that decided
    again while one was in flight would record cycles that changed nothing and
    inflate every cycle count in the file.
    """
    start = START
    harness.positions.extend([start, start, start])

    asyncio.run(harness.runner._decide())  # positioning completes; nothing dispatched
    asyncio.run(harness.runner._decide())  # dispatches, and keeps the lock
    assert harness.runner.lock.locked()

    asyncio.run(harness.runner._decide())  # blocked: nothing released the lock
    assert len(harness.pipe.sent) == 1
    assert len([r for r in harness.writer if isinstance(r, CycleRecord)]) == 2


def test_a_cycle_that_dispatches_nothing_releases_the_lock(
    harness: _Harness,
) -> None:
    """The arriving cycle sends no Action, so nothing will ever call the callback
    that releases the lock: it has to be released here or the run wedges."""
    start, target = START, TARGET
    harness.positions.extend([start, target])

    asyncio.run(harness.runner._decide())  # positioning completes
    asyncio.run(harness.runner._decide())  # arrives at the target

    assert not harness.runner.lock.locked()
    outcomes = [r for r in harness.writer if isinstance(r, TrialOutcome)]
    assert outcomes
    assert outcomes[0].result == "arrived"


# --- Ending the run ---------------------------------------------------------------


def test_a_cancelled_run_leaves_the_trial_in_flight_marked_abandoned(
    harness: _Harness,
) -> None:
    """
    How a calibration sitting actually ends: somebody stops the Session. The record
    should say the Trial was abandoned rather than trailing off after its last cycle
    and reading like a crash nobody diagnosed.
    """
    start = START
    harness.positions.extend([start, start])
    asyncio.run(harness.runner._decide())
    asyncio.run(harness.runner._decide())

    harness.runner._close_record()

    outcomes = [r for r in harness.writer if isinstance(r, TrialOutcome)]
    assert [o.result for o in outcomes] == ["abandoned"]


def test_finishing_twice_ships_one_key_release(harness: _Harness) -> None:
    """
    `_finish` disables this DecisionMaker, but the disabler thread cancels the task
    asynchronously, so further cycles can reach `_finish` first. Each one would
    otherwise send another release Action into the priority queue.
    """
    harness.runner._disable_decision_makers = lambda *names: None  # type: ignore[method-assign]

    harness.runner._finish()
    harness.runner._finish()

    assert len(harness.pipe.sent) == 1


# --- Knobs ------------------------------------------------------------------------


def test_the_first_batch_runs_on_the_production_defaults(harness: _Harness) -> None:
    assert harness.runner._throttle == TrialRunner._throttle
    assert harness.runner.data.action_duration == TrialRunner.DEFAULT_ACTION_DURATION
    assert (
        harness.runner.data.movement_handler.narrow_platform_threshold
        == _NARROW_PLATFORM_THRESHOLD
    )


def test_a_swept_batch_puts_its_knobs_in_force_and_the_next_takes_them_back(
    harness: _Harness,
) -> None:
    """
    The sweep's whole premise. Reverting off the *class* defaults rather than off
    whatever is in place is what stops batch three quietly measuring batch two.
    """
    _advance_to_batch(harness, "swept")
    assert harness.runner._throttle == 0.5
    assert harness.runner.data.action_duration == 0.25
    assert harness.runner.data.movement_handler.narrow_platform_threshold == 9

    _advance_to_batch(harness, "back-to-default")
    assert harness.runner._throttle == TrialRunner._throttle
    assert harness.runner.data.action_duration == TrialRunner.DEFAULT_ACTION_DURATION
    assert (
        harness.runner.data.movement_handler.narrow_platform_threshold
        == _NARROW_PLATFORM_THRESHOLD
    )


def test_the_action_duration_knob_reaches_the_compiler(harness: _Harness) -> None:
    """A Knob nobody threads into the compile inputs is a Knob that sweeps nothing."""
    _advance_to_batch(harness, "swept")
    harness.runner.data.update_attribute("movements")
    assert harness.runner._movement_compiler().keywords["total_duration"] == 0.25


def _advance_to_batch(harness: _Harness, name: str) -> None:
    """Close Trials until the named batch is in flight, then apply its Knobs."""
    start, target = START, TARGET
    for _ in range(10):
        batch = harness.runner._driver.batch
        assert batch is not None, f"schedule finished before reaching batch {name!r}"
        if batch.name == name:
            harness.runner._apply_knobs()
            return
        harness.runner._driver.advance(_read(start), 0.0)
        harness.runner._driver.advance(_read(target), 1.0)
    pytest.fail(f"never reached batch {name!r}")


def _read(point: tuple[float, float]) -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(*point, PositionSource.FUSED), 0.0)


def _compile_movements() -> object:
    from maple.model.mechanics import compile_movements

    return compile_movements


# --- Virtual positions and game map names (#397) ----------------------------------


def test_a_cycle_while_an_action_is_in_flight_records_a_sample(
    harness: _Harness,
) -> None:
    """
    It decides nothing and sends nothing, but its read is what the physics are
    measured from. Its read failing (no position fusion here) is an unsure sample,
    not a call to the minimap's error handler, which would send input mid-Action.
    """
    harness.positions.extend([START, START])
    asyncio.run(harness.runner._decide())  # positioning completes
    asyncio.run(harness.runner._decide())  # dispatches, and keeps the lock
    asyncio.run(harness.runner._decide())  # in flight: a sample

    assert len(harness.pipe.sent) == 1
    (sample,) = [r for r in harness.writer if isinstance(r, SampleRecord)]
    assert sample.correlation_id == "cid-0"
    assert sample.position.status == "unsure"


def test_the_path_is_planned_to_the_driver_s_target_in_virtual_px(
    harness: _Harness,
) -> None:
    assert harness.runner._virtual_target() == (16.0, 0.0)
    harness.runner._driver.advance(_read(START), 0.0)
    assert harness.runner._virtual_target() == (288.0, 0.0)


def test_a_batch_planned_without_teleport_builds_a_handler_without_it(
    harness: _Harness,
) -> None:
    """
    The physics schedule's walk and jump batches: a teleporting class would
    otherwise teleport along the walk being measured.
    """

    class _Teleporter:
        skills: ClassVar[dict[str, object]] = {"Teleport": corpus.LAB_TELEPORT}

    runner: Any = harness.runner
    runner.data.set_static("character", _Teleporter())
    runner.schedule = TrialSchedule(
        "teleport-lab",
        ENTRY.name,
        (
            TrialBatch(
                "walks", (TrialSpec("t", START, TARGET, 16.0, 60.0),), teleport=False
            ),
            TrialBatch("teleports", (TrialSpec("t", START, TARGET, 16.0, 60.0),)),
        ),
    )
    runner._driver = TrialDriver(runner.schedule, harness.writer)
    runner._applied_batch = None

    runner._apply_knobs()
    assert runner.data.movement_handler.teleport is None

    _advance_to_batch(harness, "teleports")
    assert runner.data.movement_handler.teleport is corpus.LAB_TELEPORT


class _Catalogue:
    """Resolves the one name the checks below use; anything else is unknown."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def map(self, name_or_id: object) -> object:
        if name_or_id not in ("Victoria Road: Ellinia", 10002000):
            raise LookupError(f"no map {name_or_id!r}")
        return type("MapData", (), {"id": 10002000})()


def _runner_on(map_id: int | None, schedule_map: str) -> TrialRunner:
    runner: Any = object.__new__(TrialRunner)
    data = BotData("Lab")
    data.set_static("map_id", map_id)
    data.set_static("world_map", corpus.world_map(ENTRY))
    runner.data = data
    runner.schedule = TrialSchedule(
        "s",
        schedule_map,
        (TrialBatch("b", (TrialSpec("t", START, TARGET, 16.0, 9.0),)),),
    )
    return cast(TrialRunner, runner)


def test_the_schedule_s_map_must_be_the_bot_s(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    The schedule names its map by game name; the catalogue resolves it, and the
    bot's own map id must match. Run elsewhere, the coordinates would name real
    places on the wrong map and record a plausible wrong experiment.
    """
    monkeypatch.setattr(
        "maple.decision_makers.trial_runner.Catalogue.latest", lambda: _Catalogue()
    )
    _runner_on(10002000, "Victoria Road: Ellinia")._assert_schedule_matches_map()

    with pytest.raises(TrialSpecError, match="map 100000000"):
        _runner_on(100000000, "Victoria Road: Ellinia")._assert_schedule_matches_map()
    with pytest.raises(TrialSpecError, match="no known map"):
        _runner_on(None, "Victoria Road: Ellinia")._assert_schedule_matches_map()
    with pytest.raises(TrialSpecError, match="no map 'Nowhere'"):
        _runner_on(10002000, "Nowhere")._assert_schedule_matches_map()


def test_the_record_header_names_the_physics_the_sitting_planned_with(
    harness: _Harness,
) -> None:
    """What the analyzer turns measured speeds into Calibration constants with."""
    from maple.model.mechanics.physics import Calibration

    runner: Any = harness.runner
    runner.data.set_static("map_id", 10002000)
    runner.data.set_static("calibration", Calibration(jump=0.98))
    header = runner._header()
    assert header.map_id == 10002000
    assert header.physics == corpus.LAB_PHYSICS_VALUES
    assert (header.speed_multiplier, header.jump_multiplier) == (1.0, 1.0)
    assert header.calibration == {
        "walk": 1.0,
        "jump": 0.98,
        "climb": 1.0,
        "teleport": 1.0,
    }
