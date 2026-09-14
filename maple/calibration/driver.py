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
character actually got.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import cast

from maple.calibration.records import (
    CycleRecord,
    MovementSummary,
    Phase,
    RecordSink,
    ScheduleHeader,
    SequenceSummary,
    TrialOutcome,
    TrialResult,
    summarize_plan,
    utc_now,
)
from maple.calibration.specs import TrialBatch, TrialSchedule, TrialSpec
from maple.model.mechanics.movement_mechanics_v2 import _MovementComponent


@dataclass(frozen=True)
class DefectPolicy:
    """
    How the two crude defect counters are computed.

    Both are **placeholders**, and knowingly so: issue #116 asks for a counter, and
    the real mechanism for stuck detection is issue #119's to design. What these
    numbers buy in the meantime is a file that says *how often* the loop failed to
    converge, so #119 has something measured to design against.

    * ``progress_epsilon`` - how much the best-so-far error has to improve for a
      cycle to count as progress. Minimap coordinates are a gross quantization of
      real-map pixels, so anything below a pixel is noise, not movement.
    * ``stall_cycles`` - how many consecutive cycles without progress make one stuck
      event. The streak resets after each event, so a loop stuck for 3x that long
      counts three times rather than one.
    """

    progress_epsilon: float = 1.0
    stall_cycles: int = 8


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

    def observe(self, position: tuple[int, int], error: float) -> None:
        seen = self._signs or (0, 0)
        dx = _sign(self.target[0] - position[0])
        dy = _sign(self.target[1] - position[1])
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


class TrialDriver:
    """
    Walks a `TrialSchedule` one decision cycle at a time.

    Each Trial runs in two phases. **Positioning** moves the character to the Trial's
    ``start`` and is not measured; it exists because a Trial that began somewhere
    else measured the wrong thing, and running out of its budget closes the Trial as
    `SETUP_FAILED` rather than producing a measurement nobody can trust.
    **Measuring** moves it to ``target``, and that is the phase the outcome describes.

    Nothing here reads a clock. `now` is passed in - `time.perf_counter()` on the
    live path, whatever the test says offline - which is what lets a whole schedule
    be walked deterministically.
    """

    def __init__(
        self,
        schedule: TrialSchedule,
        sink: RecordSink,
        *,
        defects: DefectPolicy | None = None,
    ) -> None:
        self.schedule = schedule
        self.sink = sink
        self.policy = defects or DefectPolicy()
        self._remaining = list(schedule.trials)
        self._batch: TrialBatch | None = None
        self._trial: TrialSpec | None = None
        self._phase = Phase.POSITIONING
        self._phase_started_at: float | None = None
        self._cycles = 0
        self._counters = _Defects(self.policy, (0, 0))
        self._last_error = math.inf
        self._started_at = utc_now()
        self.sink.write(ScheduleHeader.now(schedule.name, schedule.map_name))
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
        position: tuple[int, int],
        now: float,
        *,
        plan: tuple[_MovementComponent, ...] | tuple[MovementSummary, ...] = (),
        correlation_id: str | None = None,
        sequence: SequenceSummary | None = None,
    ) -> Verdict:
        """
        Hand over one decision cycle: where the character is, and when.

        :param position: The detected minimap position this cycle decided from.
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
        error = math.dist(position, target)
        self._cycles += 1
        self._last_error = error
        if self._phase is Phase.MEASURING:
            self._counters.observe(position, error)

        arrived = error <= trial.tolerance
        budget = (
            trial.time_budget
            if self._phase is Phase.MEASURING
            else trial.positioning_budget
        )
        expired = elapsed >= budget

        record = CycleRecord(
            schedule=self.schedule.name,
            batch=batch.name,
            trial=trial.name,
            phase=str(self._phase),
            cycle=self._cycles,
            elapsed=elapsed,
            wall_clock=utc_now(),
            position=position,
            target=target,
            error=error,
            dispatched=not (arrived or expired),
            correlation_id=correlation_id,
            plan=_as_summaries(plan),
            sequence=sequence,
        )
        self.sink.write(record)

        if self._phase is Phase.POSITIONING:
            if arrived:
                self._begin_measuring(now)
                return Verdict(dispatch=False, target=self.target, cycle=record)
            if expired:
                outcome = self._close(TrialResult.SETUP_FAILED, error, None, elapsed)
                return Verdict(
                    dispatch=False,
                    target=self.target,
                    cycle=record,
                    outcome=outcome,
                    finished=self.finished,
                )
            return Verdict(dispatch=True, target=target, cycle=record)

        if arrived:
            outcome = self._close(TrialResult.ARRIVED, error, elapsed, elapsed)
        elif expired:
            outcome = self._close(TrialResult.TIMEOUT, error, None, elapsed)
        else:
            return Verdict(dispatch=True, target=target, cycle=record)
        return Verdict(
            dispatch=False,
            target=self.target,
            cycle=record,
            outcome=outcome,
            finished=self.finished,
        )

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
        outcome = self._close(TrialResult.ABANDONED, self._last_error, None, elapsed)
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
        self._last_error = math.inf
        self._counters = _Defects(self.policy, self._trial.start)

    def _begin_measuring(self, now: float) -> None:
        assert self._trial is not None
        self._phase = Phase.MEASURING
        self._phase_started_at = now
        # The cycle counter restarts with the phase: an outcome's `cycles` is how
        # many cycles the *measured* run took, and folding in however many the walk
        # to `start` happened to need would make two Trials incomparable.
        self._cycles = 0
        self._counters = _Defects(self.policy, self._trial.target)

    def _close(
        self,
        result: TrialResult,
        final_error: float,
        time_to_arrival: float | None,
        duration: float,
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
            final_error=final_error,
            time_to_arrival=time_to_arrival,
            duration=duration,
            cycles=self._cycles,
            oscillations=self._counters.oscillations,
            stuck_events=self._counters.stuck_events,
            longest_stall=self._counters.longest_stall,
            started_at=self._started_at,
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


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)
