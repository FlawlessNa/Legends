"""
The calibration bot's single DecisionMaker: it walks a checked-in Trial schedule.

This is the thin half of the framework. Every judgement - which target the loop is
aiming at, when a Trial has arrived, when it has run out of budget, what the defect
counters say - belongs to `maple.calibration.driver.TrialDriver`, which runs offline
and is checked offline. What lives here is the plumbing the driver refuses to know
about: reading the position, computing the Path, shipping the Movement Plan, and
writing the record.

**It ships through the production path.** The Movement Plan goes out as an
`ActionRequest` carrying `controller.compile_and_send`, exactly as `Rotation` does,
so a Trial measures dispatch-time compilation, the Held-Keys Ledger and the focus
lock (ADR 0002) rather than a copy of them. A bespoke send loop here would produce
numbers that describe a system nobody runs.

The one-Action-at-a-time lock is `Rotation`'s, for `Rotation`'s reason: a decision
cycle is a *dispatched* cycle, and a runner that decided ten times while one Action
was in flight would record ten cycles that changed nothing.

**Virtual positions, and the map by its game name** (#397). Each cycle hands the
driver `current_position`, a `Reading[VirtualPosition]` (`PositionFusion`), and the
Path is planned to the driver's target in virtual px. The schedule names its map by
game name or id, resolved through the game data catalogue and checked against the
bot's own map at start. Nothing here reads `configs/maps`.

**Samples.** While an Action is in flight a cycle cannot decide, but it still reads
the position and hands it to the driver as a sample: what the physics are measured
from (`maple/calibration/analysis.py`). A sample read that fails is recorded as
unsure; it never calls the minimap's error handler, which sends input, in the
middle of the Action.
"""

import dataclasses
import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from pathlib import Path

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.screen import Reading
from botting.stop_file import request_stop
from game_data.catalogue import Catalogue
from maple.actions import priorities
from maple.calibration import (
    JsonlRecordWriter,
    RecordSink,
    ScheduleHeader,
    TrialBatch,
    TrialDriver,
    TrialSchedule,
    TrialSpecError,
    default_record_path,
    load_schedule,
)
from maple.calibration.driver import COARSE_SLACK, MINIMAP_PX
from maple.calibration.specs import schedule_map_id
from maple.model.characters.maple_skills import MapleSkill
from maple.model.navigation import Point
from maple.model.world import WorldMap
from maple.screen.position import VirtualPosition

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
        :raises TrialSpecError: The schedule's map isn't the bot's, or the bot's map
            has no minimap to read a virtual position on.
        """
        super().__init__(metadata, data, pipe)
        if not trial_schedule:
            raise ValueError(
                f"{self} needs a 'trial_schedule' setting naming a schedule under "
                "configs/trials/."
            )
        self.schedule: TrialSchedule = load_schedule(trial_schedule)
        self.lock = self._proxies.instance(repr(self), "Lock")
        self._assert_schedule_matches_map()

        self._create_minimap_attributes()
        self._last_target = self.schedule.trials[0][1].start
        self._batch_teleport = True

        path = (
            Path(record_path)
            if record_path
            else default_record_path(self.schedule.name)
        )
        self._writer: RecordSink = JsonlRecordWriter(path)
        self._driver = TrialDriver(
            self.schedule,
            self._writer,
            header=self._header(),
            coarse_slack=self._coarse_slack(),
        )
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

    async def task(self) -> None:
        """
        The decision loop, with the record closed out however it ends.

        A calibration sitting usually ends by being stopped rather than by the
        schedule running out, and a cancelled task takes the Engine down with it. The
        `finally` is what turns that into an `abandoned` outcome and a flushed file
        instead of a record that trails off mid-cycle.
        """
        try:
            await super().task()
        finally:
            self._close_record()

    async def _decide(self) -> None:
        if self._driver.finished:
            self._finish()
            return

        # One Action in flight at a time: a cycle that cannot dispatch is not a
        # decision cycle, and recording it would pad the count with nothing. Its
        # position read is a sample instead, which judges nothing.
        if not self.lock.acquire(blocking=False):
            self._driver.sample(self._sample_position(), time.monotonic())
            return

        dispatched = False
        try:
            self._apply_knobs()
            self.data.update_attribute("current_position")
            position: Reading[VirtualPosition] = self.data.current_position
            self.data.update_attribute("path")
            self.data.update_attribute("movements")

            verdict = self._driver.advance(
                position,
                time.monotonic(),
                plan=self.data.movements or (),
                correlation_id=self.correlation_id,
            )
            if verdict.outcome is not None:
                logger.info(
                    "%s Trial %r: %s (final error %s virtual px, %s cycles)",
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
        Put the current batch's Knob overrides in place, once per batch, and
        whether its Paths may cast Teleport (`TrialBatch.teleport`).

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
        self._batch_teleport = batch.teleport
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
            "%s applied batch %r knobs: %s%s",
            self,
            batch.name,
            knobs.overrides(),
            "" if batch.teleport else " (planned without teleport)",
        )

    def _teleport_skill(self) -> MapleSkill | None:
        """The character's teleport skill, unless the batch plans without it."""
        if not self._batch_teleport:
            return None
        return super()._teleport_skill()

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
        self._end_session()

    def _end_session(self) -> None:
        """
        Ask the Session to stop, as `Ctrl+C` does: through the stop file
        (`botting.stop_file`), which ends `SessionManager.launch` normally and
        has `__exit__` release every key and stop every process. The calibration
        bot has nothing left to do once its schedule has run, and would otherwise
        idle until stopped by hand.

        Nothing to ask when the Session did not publish its directory (a bot
        run outside a `SessionManager`).
        """
        session_dir = self.metadata.get("session_dir")
        if session_dir is None:
            return
        try:
            request_stop(Path(session_dir), f"schedule {self.schedule.name!r} finished")
        except OSError:
            logger.exception("Could not ask the Session to stop; stop it by hand.")

    def _close_record(self) -> None:
        """
        Close the file, marking whatever Trial was in flight as abandoned.

        Abandon before close, not after: `abandon` writes the outcome, and a closed
        writer would drop it. On a schedule that ran to its end this is a no-op -
        there is no Trial in flight to abandon, and the writer is already closed.
        """
        self._driver.abandon(time.monotonic())
        self._writer.close()

    @staticmethod
    async def _release_movement_keys(handle: int) -> None:
        """Called in Main Process as an ActionRequest procedure."""
        controller.release_keys(["left", "up", "down", "right"], handle)

    # --- Helpers ------------------------------------------------------------------

    def _virtual_target(self) -> Point:
        """
        Where the loop is heading, in virtual px: the driver's target, which
        `MovementsMixin` plans the Path to. Holds the last target once the schedule
        is done, so a cycle racing the shutdown still plans to somewhere.
        """
        target = self._driver.target
        if target is not None:
            self._last_target = target
        return float(self._last_target[0]), float(self._last_target[1])

    def _sample_position(self) -> Reading[VirtualPosition]:
        """
        One position read for a sample. A read that raises is recorded as unsure
        and left at that: the minimap's error handler, which `current_position`
        calls, sends input, and an Action is in flight.
        """
        try:
            return self._get_position()
        except ValueError as error:
            return Reading.unsure(time.monotonic(), f"sample: {error}")

    def _assert_schedule_matches_map(self) -> None:
        """
        A Trial's coordinates are virtual px on one map. Run against another map
        they name real places and produce a plausible-looking record of the wrong
        experiment, so this is a hard failure rather than a warning: the schedule's
        map, resolved through the catalogue, must be the bot's (`data.map_id`), and
        that map must have a minimap to read a virtual position on.
        """
        with Catalogue.latest() as catalogue:
            wanted = schedule_map_id(self.schedule, catalogue)
        loaded: int | None = getattr(self.data, "map_id", None)
        if loaded != wanted:
            where = "no known map" if loaded is None else f"map {loaded}"
            raise TrialSpecError(
                f"Schedule {self.schedule.name!r} is written against map "
                f"{self.schedule.map!r} ({wanted}), but {self.data.ign} is on {where}."
            )
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        if world_map is None or world_map.minimap is None:
            raise TrialSpecError(
                f"Schedule {self.schedule.name!r} needs a virtual position, and map "
                f"{wanted} has no minimap to read one on."
            )

    def _coarse_slack(self) -> float:
        """How far a minimap-only position may be off the feet, on this map."""
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        if world_map is None or world_map.minimap is None:
            return COARSE_SLACK
        return COARSE_SLACK * world_map.minimap.scale / MINIMAP_PX

    def _header(self) -> ScheduleHeader:
        """The record's first line: the map, and the physics the sitting plans with."""
        calibration = getattr(self.data, "calibration", None)
        physics = getattr(self.data, "game_physics", None)
        return ScheduleHeader.now(
            self.schedule.name,
            self.schedule.map,
            map_id=getattr(self.data, "map_id", None),
            physics=None if physics is None else dict(physics),
            speed_multiplier=float(self.data.speed_multiplier),
            jump_multiplier=float(self.data.jump_multiplier),
            calibration=(
                None if calibration is None else dataclasses.asdict(calibration)
            ),
        )
