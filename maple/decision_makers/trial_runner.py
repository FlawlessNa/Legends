"""
The calibration bot's single DecisionMaker: it walks a checked-in Trial schedule.

This is the thin half of the framework. Every judgement - which target the loop is
aiming at, when a Trial has arrived, when it has run out of budget, what the defect
counters say - belongs to `maple.calibration.driver.TrialDriver`, which runs offline
and is checked offline. What lives here is the plumbing the driver refuses to know
about: reading the minimap, computing the Path, shipping the Movement Plan, and
writing the record.

**It ships through the production path.** The Movement Plan goes out as an
`ActionRequest` carrying `controller.compile_and_send`, exactly as `Rotation` does,
so a Trial measures dispatch-time compilation, the Held-Keys Ledger and the focus
lock (ADR 0002) rather than a copy of them. A bespoke send loop here would produce
numbers that describe a system nobody runs.

The one-Action-at-a-time lock is `Rotation`'s, for `Rotation`'s reason: a decision
cycle is a *dispatched* cycle, and a runner that decided ten times while one Action
was in flight would record ten cycles that changed nothing.
"""

import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from pathlib import Path

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from maple.actions import priorities
from maple.calibration import (
    JsonlRecordWriter,
    RecordSink,
    TrialBatch,
    TrialDriver,
    TrialSchedule,
    default_record_path,
    load_schedule,
)

from .mixins import MinimapAttributesMixin, MovementsMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class TrialRunner(MinimapAttributesMixin, MovementsMixin, DecisionMaker):
    """
    Walks a `TrialSchedule` through the production decide -> compile -> send path.

    One of these is the whole calibration bot (`maple.bots.CalibrationBot`). It is
    deliberately not a `Rotation` subclass: a rotation picks its own next target and
    never stops, and both of those are exactly what a Trial must not do.
    """

    #: The default decision-loop interval, and the `decision_interval` Knob's default.
    #: Matches `Rotation`, so an unswept batch measures what production does.
    _throttle = 0.1

    #: The default Action duration cap, and the `action_duration` Knob's default.
    DEFAULT_ACTION_DURATION = 1.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        trial_schedule: str = "",
        record_path: str | None = None,
        **kwargs: object,
    ) -> None:
        """
        :param trial_schedule: Name of a schedule under `configs/trials/` (or a path
            to one). Required - there is nothing for this DecisionMaker to do
            without it.
        :param record_path: Where to write the Trial record. Defaults to a
            timestamped file under `trial_records/`, which is gitignored: a record is
            measured on one machine against one client and means nothing checked in.
        """
        super().__init__(metadata, data, pipe)
        if not trial_schedule:
            raise ValueError(
                f"{self} needs a 'trial_schedule' setting naming a schedule under "
                "configs/trials/."
            )
        self.schedule: TrialSchedule = load_schedule(trial_schedule)
        self.lock = self._proxies.instance(repr(self), "Lock")

        self._create_minimap_attributes()
        self._assert_schedule_matches_map()

        # `next_target` is normally the rotation's to own; here the driver owns it,
        # and the pathing attributes below read it. It has to exist first.
        self.data.create_or_reconfigure_attribute(
            "next_target",
            self._driver_target,
            initial_value=self.schedule.trials[0][1].start,
        )
        self.data.set_feature("has_rotation_attributes")
        self._last_target = self.schedule.trials[0][1].start

        path = (
            Path(record_path)
            if record_path
            else default_record_path(self.schedule.name)
        )
        self._writer: RecordSink = JsonlRecordWriter(path)
        self._driver = TrialDriver(self.schedule, self._writer)
        self._applied_batch: TrialBatch | None = None
        self._finished = False
        self._apply_knobs()
        logger.info(
            "%s will walk %s Trial(s) from schedule %r; recording to %s",
            self,
            len(self.schedule.trials),
            self.schedule.name,
            path,
        )

    # --- the decision cycle -------------------------------------------------------

    async def task(self, *args: object, **kwargs: object) -> None:
        """
        The decision loop, with the record closed out however it ends.

        A calibration sitting usually ends by being stopped rather than by the
        schedule running out, and a cancelled task takes the Engine down with it. The
        `finally` is what turns that into an `abandoned` outcome and a flushed file
        instead of a record that trails off mid-cycle.
        """
        try:
            await super().task(*args, **kwargs)
        finally:
            self._close_record()

    async def _decide(self) -> None:
        if self._driver.finished:
            self._finish()
            return

        # One Action in flight at a time: a cycle that cannot dispatch is not a
        # decision cycle, and recording it would pad the count with nothing.
        if not self.lock.acquire(blocking=False):
            return

        dispatched = False
        try:
            self._apply_knobs()
            self.data.update_attribute("current_minimap_position")
            position = self.data.current_minimap_position
            self.data.update_attribute("next_target")
            self.data.update_attribute("movements")

            verdict = self._driver.advance(
                position,
                time.perf_counter(),
                plan=self.data.movements or (),
                correlation_id=self.correlation_id,
            )
            if verdict.outcome is not None:
                logger.info(
                    "%s Trial %r: %s (final error %.2f, %s cycles)",
                    self,
                    verdict.outcome.trial,
                    verdict.outcome.result,
                    verdict.outcome.final_error,
                    verdict.outcome.cycles,
                )
            if verdict.dispatch and self._has_movements():
                self.send(self._request())
                dispatched = True
        finally:
            if not dispatched:
                self.lock.release()

    def _request(self) -> ActionRequest:
        """The same Action `Rotation` sends: a Movement Plan, compiled at dispatch."""
        return ActionRequest(
            f"{self}",
            controller.compile_and_send,
            ign=self.data.ign,
            requeue_if_not_scheduled=False,
            callbacks=[self.lock.release],
            args=(self.data.handle, self._movement_compiler()),
        )

    # --- Knobs --------------------------------------------------------------------

    def _apply_knobs(self) -> None:
        """
        Put the current batch's Knob overrides in place, once per batch.

        Re-checked every cycle rather than at batch boundaries only, because the
        driver decides when a batch ends and this side should not have to track it.
        Reapplying is a no-op once the batch is the one already applied.
        """
        batch = self._driver.batch
        if batch is None or batch is self._applied_batch:
            return
        knobs = batch.knobs
        # Off the *class* default, never off the value in place: a batch that sweeps
        # a Knob must not leave it swept for the next batch that does not.
        self._throttle = (
            type(self)._throttle
            if knobs.decision_interval is None
            else knobs.decision_interval
        )
        self._create_pathing_attributes(
            duration=(
                self.DEFAULT_ACTION_DURATION
                if knobs.action_duration is None
                else knobs.action_duration
            ),
            narrow_platform_threshold=knobs.precision_threshold,
            edge_departure_threshold=knobs.edge_departure_threshold,
        )
        # `_create_pathing_attributes` only reconfigures how the handler is built; the
        # instance already held would otherwise keep the previous batch's threshold
        # (and its caches) for the rest of the run.
        self.data.update_attribute("movement_handler")
        self._applied_batch = batch
        logger.info(
            "%s applied batch %r knobs: %s", self, batch.name, knobs.overrides()
        )

    # --- Finishing ----------------------------------------------------------------

    def _finish(self) -> None:
        """
        Close the record and stop deciding.

        Idempotent: the disable below takes effect when the disabler thread cancels
        the task, so one or more further cycles may reach here first, and each would
        otherwise ship another key-release Action.

        The direction keys are dropped through an `ActionRequest` rather than here:
        an Engine may not send input, so this mirrors `Bot.pause`'s handoff to Main
        Process. Without it a schedule ending mid-walk leaves a key down, which is a
        Held-Keys Ledger entry nobody will clear.
        """
        if self._finished:
            return
        self._finished = True
        self._writer.close()
        logger.info("%s finished schedule %r.", self, self.schedule.name)
        self.send(
            ActionRequest(
                f"{self} - Releasing movement keys",
                self._release_movement_keys,
                ign=self.data.ign,
                priority=priorities.FAILSAFE,
                requeue_if_not_scheduled=True,
                cancels_itself=True,
                args=(self.data.handle,),
            )
        )
        self._disable_decision_makers(type(self).__name__)

    def _close_record(self) -> None:
        """
        Close the file, marking whatever Trial was in flight as abandoned.

        Abandon before close, not after: `abandon` writes the outcome, and a closed
        writer would drop it. On a schedule that ran to its end this is a no-op -
        there is no Trial in flight to abandon, and the writer is already closed.
        """
        self._driver.abandon(time.perf_counter())
        self._writer.close()

    @staticmethod
    async def _release_movement_keys(handle: int) -> None:
        """Called in Main Process as an ActionRequest procedure."""
        controller.release_keys(["left", "up", "down", "right"], handle)

    # --- Helpers ------------------------------------------------------------------

    def _driver_target(self) -> tuple[int, int]:
        """
        Where the loop is heading, as the `next_target` attribute the pathing
        attributes read. Holds the last target once the schedule is done, so a cycle
        racing the shutdown still computes a Path rather than pathing to `None`.
        """
        target = self._driver.target
        if target is not None:
            self._last_target = target
        return self._last_target

    def _assert_schedule_matches_map(self) -> None:
        """
        A Trial's coordinates are minimap coordinates. Run against another map they
        name real, walkable nodes and produce a plausible-looking record of the wrong
        experiment, so this is a hard failure rather than a warning.
        """
        loaded = self.data.current_minimap.map_name
        if loaded != self.schedule.map_name:
            raise ValueError(
                f"Schedule {self.schedule.name!r} is written against map "
                f"{self.schedule.map_name!r}, but {self.data.ign} is on {loaded!r}."
            )
