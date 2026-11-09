import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import time

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.screen import Status
from maple.actions import priorities, toggle_menu
from maple.screen.chat import CHAT
from maple.telemetry_events import (
    RECOVERY_MOB_SPAWN_RESTORED,
    MobSpawnRestoredPayload,
)

from .mixins import MobsHittingMixin, NextTargetMixin, ReactionsMixin, UIMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class CheckMobsStillSpawn(
    MobsHittingMixin, UIMixin, NextTargetMixin, ReactionsMixin, DecisionMaker
):
    _throttle = 3.0
    FAILSAFE_TIMER = 30.0
    screen_readers = (CHAT,)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        mob_spawn_alert_timer: float,
        mob_spawn_alert_threshold: int,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._alert_timer = mob_spawn_alert_timer
        self._alert_threshold = mob_spawn_alert_threshold
        self._last_valid_detection = time.perf_counter() + 30.0

        self._condition = self._proxies.instance(repr(self), "Condition")

    async def task(self) -> None:
        self._last_valid_detection = time.perf_counter() + 10.0
        await super().task()

    async def _decide(self) -> None:
        mob_count = self.mob_count_in_img(
            self.data.current_frame.pixels, self.data.current_mobs, debug=True
        )

        # Enough mobs, reset timer
        if mob_count >= self._alert_threshold:
            self._last_valid_detection = time.perf_counter()

        # Not enough mobs and timer expired
        elif time.perf_counter() - self._last_valid_detection >= self._alert_timer:
            logger.warning("No mobs detected in %s seconds.", self._alert_timer)
            try:
                await self._setup_failsafe_procedure()
                await asyncio.wait_for(
                    self._failsafe_procedure(), timeout=self.FAILSAFE_TIMER
                )
                restored: MobSpawnRestoredPayload = {
                    "alert_timer": float(self._alert_timer),
                    "alert_threshold": int(self._alert_threshold),
                }
                self.emit(RECOVERY_MOB_SPAWN_RESTORED, restored)
                await self._clear_failsafe_procedure()

            except TimeoutError:
                # Failsafe procedure failed. Pause bot and send final chat reaction
                self._disable_decision_makers(
                    "Rotation", "CheckMobsStillSpawn", "CheckStillInMap"
                )
                self._react("advanced")
                logger.critical(
                    "Failed to ensure mobs still spawn after %s seconds",
                    self.FAILSAFE_TIMER,
                )

    async def _setup_failsafe_procedure(self) -> None:
        self._disable_decision_makers("MobsHitting", "TelecastMobsHitting")
        await self._validate_request_async(
            self._toggle_chat_request(),
            lambda: self._chat_shown() is False,
            timeout=5.0,
        )
        self.data.snapshot_attribute("next_target")
        if self.data.current_minimap.feature_cycle:
            self.data.reconfigure_attribute(
                "next_target",
                update_function=self._update_next_target_from_cycle,
            )
        else:
            self.data.reconfigure_attribute(
                "next_target",
                update_function=self.data.current_minimap.random_point,
            )

    async def _clear_failsafe_procedure(self) -> None:
        await self._validate_request_async(
            self._toggle_chat_request(),
            lambda: self._chat_shown() is True,
            timeout=5.0,
        )
        self._enable_decision_makers("MobsHitting", "TelecastMobsHitting")
        self._last_valid_detection = time.perf_counter()
        self._restore_rotation_target()  # This resets the next_target procedure

    async def _failsafe_procedure(self) -> None:
        try:
            await asyncio.wait_for(
                self._rotate_until_mobs_detected(), timeout=self.FAILSAFE_TIMER // 2
            )
        except TimeoutError:
            # Still no mobs.
            self._react("light")
            logger.warning(
                "No mobs detected after %s seconds", self.FAILSAFE_TIMER // 2
            )

            # Keep trying until this is cancelled by the failsafe procedure
            await self._rotate_until_mobs_detected()

    async def _rotate_until_mobs_detected(self) -> None:
        while True:
            mob_count = self.mob_count_in_img(
                self.data.current_frame.pixels, self.data.current_mobs, debug=False
            )
            logger.debug("%s sees %s mob(s).", self.data.ign, mob_count)
            if mob_count >= self._alert_threshold:
                break
            await asyncio.sleep(0.5)

    def _chat_shown(self) -> bool | None:
        """
        Whether the chat log is shown in a fresh frame, from the bot's
        `chat_reader`; `None` when that can't be read (covered, or an unusable
        frame), which neither validation accepts.
        """
        self.data.update_attribute("current_frame")
        reading = self.data.chat_reader.shown(self.data.current_frame)
        if reading.status is not Status.READ:
            logger.debug(
                "%s can't tell whether the chat is shown: %s (%s)",
                self,
                reading.status.value,
                reading.detail,
            )
            return None
        return reading.value

    def _toggle_chat_request(self) -> ActionRequest:
        return ActionRequest(
            f"{self} - Toggle Chat",
            toggle_menu,
            self.data.ign,
            priorities.ANTI_DETECTION,
            block_lower_priority=True,
            args=(self.data.handle, self.data.ign, "Chat Toggle"),
        )
