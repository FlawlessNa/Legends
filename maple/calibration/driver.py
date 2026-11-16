"""
The `TrialDriver`: the calibration bot's brain, with no bot around it.

Everything a Trial *decides* lives here - which target the loop is aiming at, when
a Trial has arrived, when it has run out of budget, what the defect counters say -
and none of what it takes to run one: no client, no screenshot, no pipe, no clock of
its own. The driver is fed a position and a time, and answers.

That is the whole point of the seam. A calibration bot cannot be checked offline;
this can, against synthetic position streams and against positions walked off a real
Corpus map, which is what makes the framework's acceptance an offline one. The
DecisionMaker on the other side of the seam (`maple/decision_makers/trial_runner.py`)
holds the plumbing and no judgement.

The driver's contract is one call per decision cycle::

    verdict = driver.advance(position, now, plan=movements, correlation_id=...)

`advance` records the cycle, then judges it, and the `Verdict` says what the loop
should do next. Judging *after* recording is deliberate: the arriving cycle is a
cycle, and a file whose last line is the one before arrival cannot say how close the
character actually got. Between cycles, while an Action is in flight, `sample`
records the position reads the physics are measured from, and judges nothing.

**Positions are `Reading[VirtualPosition]`, in virtual px** (#397). A position that
was not read (`UNSURE`, or anything but `READ`) is recorded as such and judges
nothing: no arrival, no progress, no oscillation, and no dispatch (C-NOGUESS);
only the budget still runs. A ``coarse`` position (the minimap's alone, the middle
of the canvas pixel the feet are in) arrives only when its whole canvas pixel lies
inside the tolerance (`TrialDriver.coarse_slack`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final, cast

from botting.screen import Reading
from maple.calibration.records import (
    CycleRecord,
    MovementSummary,
    Phase,
    PositionRecord,
    RecordSink,
    SampleRecord,
    ScheduleHeader,
    SequenceSummary,
    TrialOutcome,
    TrialResult,
    summarize_plan,
    utc_now,
)
from maple.calibration.specs import TrialBatch, TrialSchedule, TrialSpec
from maple.model.mechanics.movement_mechanics_v2 import _MovementComponent
from maple.screen.position import PositionSource, VirtualPosition

#: Virtual px per minimap (canvas) px on the MSCW minimap (`mag` 4, so 2**4). The
#: driver judged in minimap px until #397; its defaults below are the old values
#: converted at this scale, not new tunings.
MINIMAP_PX: Final = 16.0

#: How far a ``coarse`` position may be from the feet: from the middle of its
#: canvas pixel to a corner, half a pixel on each axis.
COARSE_SLACK: Final = MINIMAP_PX / 2 * math.sqrt(2)

#: How many times one move of the positioning Path may fail before the Trial
#: closes as `SETUP_FAILED`, rather than when the setup budget runs out (#509).
#: The precision-movement taxonomy's tightest rows (PM1 to PM3) give a move 3
#: Attempts (`docs/planning/precision-movement-taxonomy.md`), and production's
#: Reaction Ladder abandons a target on the third failure (2 Reflexes, then
#: Abandon: `RecoveryThresholds.reflex_attempts`). The live records of
#: 2026-11-13 replayed through it: `gap-right-1` gives up at 27 s instead of
#: 61, the `branch-` setups at 8 s instead of 60, and no Trial that arrived is
#: cut short; `branch-right-1` failed one jump twice, then arrived, so 2 would.
SETUP_MOVE_FAILURES: Final = 3

#: How near two moves' take-offs, and their landings, lie to be one move, in
#: virtual px: one minimap px. A replan from a fresh read moves a take-off by
#: less; a different take-off on the same platform is another move.
SAME_MOVE_PX: Final = MINIMAP_PX

#: Movement Plan components that travel along one surface; every other one is
#: a move between two (a jump, a drop, a teleport, a portal).
_TRAVEL: Final = frozenset({"WALK_LEFT", "WALK_RIGHT", "CLIMB_UP", "CLIMB_DOWN"})


@dataclass(frozen=True)
class DefectPolicy:
    """
    How the two crude defect counters are computed.

    Both are **placeholders**, and knowingly so: issue #116 asks for a counter, and
    the real mechanism for stuck detection is issue #119's to design. What these
    numbers buy in the meantime is a file that says *how often* the loop failed to
    converge, so #119 has something measured to design against.

    * ``progress_epsilon`` - how much the best-so-far error, in virtual px, has to
      improve for a cycle to count as progress. It was 1 minimap px, below which a
      minimap read is noise; converted, that is `MINIMAP_PX`. Left there rather
      than refitted to the play-area read's precision, which is #120's to fit.
    * ``stall_cycles`` - how many consecutive cycles without progress make one stuck
      event. The streak resets after each event, so a loop stuck for 3x that long
      counts three times rather than one.
    * ``level_band`` - how close to the target, on one axis and in virtual px, counts
      as level with it rather than to one side. In minimap px, level meant the same
      pixel; converted, that is half a pixel either side. Without it, jitter about
      a target the character stands level with would count as oscillation.
    """

    progress_epsilon: float = MINIMAP_PX
    stall_cycles: int = 8
    level_band: float = MINIMAP_PX / 2


@dataclass
class _Defects:
    """
    Oscillation and stall counting for one measured phase.

    Oscillation is read off the **sign of the displacement to the target**, per axis,
    rather than off the distance: a character orbiting the target at a constant
    distance is oscillating, and an unsigned error would call it a stall. A cycle
    counts once however many axes flipped in it - two axes flipping together is one
    overshoot, not two.
    """

    policy: DefectPolicy
    target: tuple[int, int]
    oscillations: int = 0
    stuck_events: int = 0
    longest_stall: int = 0
    _signs: tuple[int, int] | None = field(default=None, init=False)
    _best_error: float | None = field(default=None, init=False)
    _stall: int = field(default=0, init=False)

    def observe(self, position: tuple[float, float], error: float) -> None:
        seen = self._signs or (0, 0)
        band = self.policy.level_band
        dx = _sign(self.target[0] - position[0], band)
        dy = _sign(self.target[1] - position[1], band)
        if (dx != 0 and seen[0] != 0 and dx != seen[0]) or (
            dy != 0 and seen[1] != 0 and dy != seen[1]
        ):
            self.oscillations += 1
        # A zero component means "level with the target on this axis", which is not a
        # direction and must not erase the direction last seen; carry the old sign.
        self._signs = (dx or seen[0], dy or seen[1])

        improved = (
            self._best_error is None
            or error < self._best_error - self.policy.progress_epsilon
        )
        if improved:
            self._best_error = error
            self._stall = 0
            return
        self._stall += 1
        self.longest_stall = max(self.longest_stall, self._stall)
        if self._stall >= self.policy.stall_cycles:
            self.stuck_events += 1
            self._stall = 0


@dataclass(frozen=True)
class Verdict:
    """
    What the loop should do with the cycle it just handed over.

    ``dispatch`` is the only field a runner has to act on; the rest is there so a
    test - or a future analyzer running the driver over a replayed record - can see
    the same state transition the runner saw.
    """

    #: True when the Trial is still running and the plan should be sent.
    dispatch: bool
    #: The target the *next* cycle should aim at; None when the schedule is done.
    target: tuple[int, int] | None
    #: The record this cycle produced, or None when the schedule was already done.
    cycle: CycleRecord | None = None
    #: Set on the cycle that closed a Trial.
    outcome: TrialOutcome | None = None
    #: True once every Trial in the schedule has been closed.
    finished: bool = False


@dataclass
class _MoveFailures:
    """
    Which move of the positioning Path keeps failing (#509), read off the
    cycles' Movement Plans alone. A plan's *next move* is its first component
    that is no walk or climb, and its *lead* the walking and climbing before
    it. When a later plan opens on the move after it, the move worked; on the
    same move, it is still under way, unless its lead grew by more than
    `SAME_MOVE_PX`: the character fell back short of it, or went past it. On
    any other move, it failed and the character is somewhere else. A plan with
    no move left worked too, and a cycle with no plan judges nothing.

    This is no Attempt count (`toolkit/movement_attempts.py`): it reads no
    position, and needs none to see a Path start over somewhere else.
    """

    _failures: list[tuple[MovementSummary, int]] = field(
        default_factory=list, init=False
    )
    _next: MovementSummary | None = field(default=None, init=False)
    _after: MovementSummary | None = field(default=None, init=False)
    _lead: float = field(default=0.0, init=False)

    def observe(self, plan: tuple[MovementSummary, ...]) -> MovementSummary | None:
        """
        Take one cycle's plan: the move that has now failed
        `SETUP_MOVE_FAILURES` times, or `None`.
        """
        if not plan:
            return None
        moves = [
            k
            for k, c in enumerate(plan)
            if c.movement_type not in _TRAVEL
            and c.start is not None
            and c.end is not None
        ]
        previous, expected, lead = self._next, self._after, self._lead
        self._next = plan[moves[0]] if moves else None
        self._after = plan[moves[1]] if len(moves) > 1 else None
        self._lead = sum(c.length for c in plan[: moves[0] if moves else 0])
        first = self._next
        if (
            previous is None
            or first is None
            or (_same_move(first, previous) and self._lead <= lead + SAME_MOVE_PX)
            or (expected is not None and _same_move(first, expected))
        ):
            return None
        for k, (move, count) in enumerate(self._failures):
            if _same_move(move, previous):
                break
        else:
            k, move, count = len(self._failures), previous, 0
            self._failures.append((move, count))
        self._failures[k] = (move, count + 1)
        return move if count + 1 >= SETUP_MOVE_FAILURES else None


def _same_move(a: MovementSummary, b: MovementSummary) -> bool:
    """One kind of move, taking off and landing within `SAME_MOVE_PX`."""
    return (
        a.movement_type == b.movement_type
        and a.start is not None
        and b.start is not None
        and a.end is not None
        and b.end is not None
        and math.dist(a.start, b.start) <= SAME_MOVE_PX
        and math.dist(a.end, b.end) <= SAME_MOVE_PX
    )


class TrialDriver:
    """
    Walks a `TrialSchedule` one decision cycle at a time.

    Each Trial runs in two phases. **Positioning** moves the character to the Trial's
    ``start`` and is not measured; it exists because a Trial that began somewhere
    else measured the wrong thing, and running out of its budget closes the Trial as
    `SETUP_FAILED` rather than producing a measurement nobody can trust. So does
    one move of its Path failing `SETUP_MOVE_FAILURES` times (`_MoveFailures`):
    the planner, which keeps no memory of a failure, would plan it again until
    the budget ran out (#509).
    **Measuring** moves it to ``target``, and that is the phase the outcome describes.

    Nothing here reads a clock. `now` is passed in - `time.monotonic()` on the
    live path, whatever the test says offline - which is what lets a whole schedule
    be walked deterministically.

    :param header: The file's first line; the runner's names the map id and the
        physics the sitting planned with. By default, one naming the schedule and
        its map only.
    :param coarse_slack: Virtual px a ``coarse`` position may be off the feet
        (`COARSE_SLACK` on the MSCW minimap).
    """

    def __init__(
        self,
        schedule: TrialSchedule,
        sink: RecordSink,
        *,
        defects: DefectPolicy | None = None,
        header: ScheduleHeader | None = None,
        coarse_slack: float = COARSE_SLACK,
    ) -> None:
        self.schedule = schedule
        self.sink = sink
        self.policy = defects or DefectPolicy()
        self.coarse_slack = coarse_slack
        self._remaining = list(schedule.trials)
        self._batch: TrialBatch | None = None
        self._trial: TrialSpec | None = None
        self._phase = Phase.POSITIONING
        self._phase_started_at: float | None = None
        self._cycles = 0
        self._unsure = 0
        self._counters = _Defects(self.policy, (0, 0))
        self._move_failures = _MoveFailures()
        self._last_error: float | None = None
        self._in_flight: str | None = None
        self._started_at = utc_now()
        self.sink.write(header or ScheduleHeader.now(schedule.name, schedule.map))
        self._arm_next()

    # --- what the runner asks -----------------------------------------------------

    @property
    def finished(self) -> bool:
        """True once every Trial has been closed and there is nothing left to aim at."""
        return self._trial is None

    @property
    def trial(self) -> TrialSpec | None:
        """The Trial in flight, or None when the schedule is done."""
        return self._trial

    @property
    def batch(self) -> TrialBatch | None:
        """The batch the Trial in flight belongs to - the one whose Knobs apply."""
        return self._batch

    @property
    def phase(self) -> Phase:
        """Which half of the Trial in flight is running."""
        return self._phase

    @property
    def target(self) -> tuple[int, int] | None:
        """
        Where the loop should be heading right now: the Trial's ``start`` while
        positioning, its ``target`` while measuring, None when the schedule is done.
        """
        if self._trial is None:
            return None
        return (
            self._trial.start
            if self._phase is Phase.POSITIONING
            else self._trial.target
        )

    # --- the cycle ----------------------------------------------------------------

    def advance(
        self,
        position: Reading[VirtualPosition],
        now: float,
        *,
        plan: tuple[_MovementComponent, ...] | tuple[MovementSummary, ...] = (),
        correlation_id: str | None = None,
        sequence: SequenceSummary | None = None,
    ) -> Verdict:
        """
        Hand over one decision cycle: where the character is, and when.

        :param position: The virtual position this cycle decided from, as read:
            one that was not read judges nothing (the module docstring).
        :param now: A monotonic reading, in seconds. Only differences are used.
        :param plan: The Movement Plan this cycle chose, either as compiled
            components or already summarized.
        :param correlation_id: The `_decide()` call's id - the join key into the
            Session's `action.*` telemetry for this same cycle.
        :param sequence: The compiled Input Sequence's summary, where the caller
            compiled for itself. `None` on the live path, where compilation happens
            in Main Process at dispatch and the Engine never sees the result.
        :return: What to do next.
        """
        trial, batch = self._trial, self._batch
        if trial is None or batch is None:
            return Verdict(dispatch=False, target=None, finished=True)

        if self._phase_started_at is None:
            self._phase_started_at = now
        elapsed = now - self._phase_started_at
        target = trial.target if self._phase is Phase.MEASURING else trial.start
        self._cycles += 1
        value = position.value
        error: float | None = None
        arrived = False
        if value is None:
            if self._phase is Phase.MEASURING:
                self._unsure += 1
        else:
            xy = (float(value.x), float(value.y))
            error = math.dist(xy, target)
            self._last_error = error
            if self._phase is Phase.MEASURING:
                self._counters.observe(xy, error)
            slack = self.coarse_slack if value.source is PositionSource.COARSE else 0.0
            arrived = error + slack <= trial.tolerance

        budget = (
            trial.time_budget
            if self._phase is Phase.MEASURING
            else trial.positioning_budget
        )
        expired = elapsed >= budget
        gave_up = (
            self._move_failures.observe(_as_summaries(plan))
            if self._phase is Phase.POSITIONING and value is not None and not arrived
            else None
        )
        dispatch = value is not None and not (arrived or expired or gave_up is not None)

        record = CycleRecord(
            schedule=self.schedule.name,
            batch=batch.name,
            trial=trial.name,
            phase=str(self._phase),
            cycle=self._cycles,
            elapsed=elapsed,
            wall_clock=utc_now(),
            position=PositionRecord.of(position),
            target=target,
            error=error,
            dispatched=dispatch,
            correlation_id=correlation_id,
            plan=_as_summaries(plan),
            sequence=sequence,
        )
        self.sink.write(record)
        if dispatch:
            self._in_flight = correlation_id

        if self._phase is Phase.POSITIONING:
            if arrived:
                self._begin_measuring(now)
                return Verdict(dispatch=False, target=self.target, cycle=record)
            if expired or gave_up is not None:
                outcome = self._close(
                    TrialResult.SETUP_FAILED, None, elapsed, failed_move=gave_up
                )
                return Verdict(
                    dispatch=False,
                    target=self.target,
                    cycle=record,
                    outcome=outcome,
                    finished=self.finished,
                )
            return Verdict(dispatch=dispatch, target=target, cycle=record)

        if arrived:
            outcome = self._close(TrialResult.ARRIVED, elapsed, elapsed)
        elif expired:
            outcome = self._close(TrialResult.TIMEOUT, None, elapsed)
        else:
            return Verdict(dispatch=dispatch, target=target, cycle=record)
        return Verdict(
            dispatch=False,
            target=self.target,
            cycle=record,
            outcome=outcome,
            finished=self.finished,
        )

    def sample(
        self, position: Reading[VirtualPosition], now: float
    ) -> SampleRecord | None:
        """
        Record one position read between decision cycles, while an Action is in
        flight. It judges nothing: arrival, budgets and defects stay the decision
        cycles' (`advance`). `None` when no Trial is in flight.

        :param position: The position as read, unsure or not.
        :param now: The same clock `advance` is given.
        """
        trial, batch = self._trial, self._batch
        if trial is None or batch is None:
            return None
        started = now if self._phase_started_at is None else self._phase_started_at
        record = SampleRecord(
            schedule=self.schedule.name,
            batch=batch.name,
            trial=trial.name,
            phase=str(self._phase),
            elapsed=now - started,
            position=PositionRecord.of(position),
            correlation_id=self._in_flight,
        )
        self.sink.write(record)
        return record

    def abandon(self, now: float) -> TrialOutcome | None:
        """
        Close the Trial in flight without a verdict - the schedule was cut short.

        Used when a run ends from outside (a Session stopped, a `KeyboardInterrupt`),
        so the file says the Trial was abandoned rather than trailing off mid-cycle
        and reading like a crash nobody diagnosed. Trials not yet started are simply
        dropped: they were never run, and an outcome for one would be a fabrication.
        """
        if self._trial is None:
            return None
        elapsed = (
            0.0 if self._phase_started_at is None else now - self._phase_started_at
        )
        outcome = self._close(TrialResult.ABANDONED, None, elapsed)
        self._remaining.clear()
        self._trial = None
        self._batch = None
        return outcome

    # --- state transitions --------------------------------------------------------

    def _arm_next(self) -> None:
        if not self._remaining:
            self._trial = None
            self._batch = None
            return
        self._batch, self._trial = self._remaining.pop(0)
        self._phase = Phase.POSITIONING
        self._phase_started_at = None
        self._cycles = 0
        self._unsure = 0
        self._last_error = None
        self._in_flight = None
        self._counters = _Defects(self.policy, self._trial.start)
        self._move_failures = _MoveFailures()

    def _begin_measuring(self, now: float) -> None:
        assert self._trial is not None
        self._phase = Phase.MEASURING
        self._phase_started_at = now
        # The cycle counter restarts with the phase: an outcome's `cycles` is how
        # many cycles the *measured* run took, and folding in however many the walk
        # to `start` happened to need would make two Trials incomparable.
        self._cycles = 0
        self._unsure = 0
        self._in_flight = None
        self._counters = _Defects(self.policy, self._trial.target)

    def _close(
        self,
        result: TrialResult,
        time_to_arrival: float | None,
        duration: float,
        *,
        failed_move: MovementSummary | None = None,
    ) -> TrialOutcome:
        assert self._trial is not None
        assert self._batch is not None
        outcome = TrialOutcome(
            schedule=self.schedule.name,
            batch=self._batch.name,
            trial=self._trial.name,
            knobs=self._batch.knobs,
            start=self._trial.start,
            target=self._trial.target,
            tolerance=self._trial.tolerance,
            time_budget=self._trial.time_budget,
            result=str(result),
            final_error=self._last_error,
            time_to_arrival=time_to_arrival,
            duration=duration,
            cycles=self._cycles,
            oscillations=self._counters.oscillations,
            stuck_events=self._counters.stuck_events,
            longest_stall=self._counters.longest_stall,
            started_at=self._started_at,
            unsure_cycles=self._unsure,
            measures=None
            if self._trial.measures is None
            else str(self._trial.measures),
            failed_move=failed_move,
        )
        self.sink.write(outcome)
        self._arm_next()
        return outcome


def _as_summaries(
    plan: tuple[_MovementComponent, ...] | tuple[MovementSummary, ...],
) -> tuple[MovementSummary, ...]:
    """
    Accept a Movement Plan either way round.

    The runner has compiled components to hand; a replay reading a record back has
    summaries already. Taking both keeps the caller from converting just to be
    converted again.
    """
    if not plan:
        return ()
    if isinstance(plan[0], MovementSummary):
        return cast("tuple[MovementSummary, ...]", plan)
    return summarize_plan(cast("tuple[_MovementComponent, ...]", plan))


def _sign(value: float, band: float) -> int:
    """The side ``value`` is on, 0 within ``band`` of level."""
    if abs(value) < band:
        return 0
    return 1 if value > 0 else -1
