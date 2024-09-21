import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import time

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker
from royals.actions import priorities, toggle_menu
from .mixins import (
    UIMixin,
    MobsHittingMixin,
    NextTargetMixin,
    ReactionsMixin
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class CheckMobsStillSpawn(
    MobsHittingMixin, UIMixin, NextTargetMixin, ReactionsMixin, DecisionMaker
):
    _throttle = 3.0
    FAILSAFE_TIMER = 30.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        mob_spawn_alert_timer: float,
        mob_spawn_alert_threshold: int,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._alert_timer = mob_spawn_alert_timer
        self._alert_threshold = mob_spawn_alert_threshold
        self._last_valid_detection = time.perf_counter() + 30.0

        self._condition = self.request_proxy(self.metadata, f"{self}", "Condition")
        if not self.data.has_chat_feed_attributes:
            self._create_chat_feed_attributes()

    async def task(self, *args, **kwargs) -> None:
        self._last_valid_detection = time.perf_counter() + 10.0
        await super().task(*args, **kwargs)

    async def _decide(self) -> None:
        mob_count = self.mob_count_in_img(
            self.data.current_client_img,
            self.data.current_mobs,
            debug=False
        )

        # Enough mobs, reset timer
        if mob_count >= self._alert_threshold:
            self._last_valid_detection = time.perf_counter()

        # Not enough mobs and timer expired
        elif time.perf_counter() - self._last_valid_detection >= self._alert_timer:
            logger.log(
                LOG_LEVEL, f"No mobs detected in {self._alert_timer} seconds."
            )
            try:
                await self._setup_failsafe_procedure()
                await asyncio.wait_for(
                    self._failsafe_procedure(), timeout=self.FAILSAFE_TIMER
                )
                logger.log(
                    LOG_LEVEL, "Mobs still spawn. Resuming normal operation."
                )
                await self._clear_failsafe_procedure()

            except asyncio.TimeoutError:
                # Failsafe procedure failed. Pause bot and send final chat reaction
                self._disable_decision_makers(
                    "Rotation",
                    "CheckMobsStillSpawn",
                    "CheckStillInMap"
                )
                self._react("advanced")
                logger.critical(
                    f"Failed to ensure mobs still spawn after {self.FAILSAFE_TIMER} "
                    f"seconds"
                )

    async def _setup_failsafe_procedure(self) -> None:
        self._disable_decision_makers(
            "MobsHitting",
            "TelecastMobsHitting",
            "PartyRebuff"
        )
        await self._validate_request_async(
            self._toggle_chat_request(),
            lambda: not self.data.chat_feed.is_displayed(self.data.handle),
            timeout=5.0,
        )
        if self.data.current_minimap.feature_cycle:
            self.data.create_attribute(
                "next_target",
                self._update_next_target_from_cycle,
            )
        else:
            self.data.create_attribute(
                "next_target",
                self.data.current_minimap.random_point(),
            )

    async def _clear_failsafe_procedure(self) -> None:
        await self._validate_request_async(
            self._toggle_chat_request(),
            lambda: self.data.chat_feed.is_displayed(self.data.handle),
            timeout=5.0,
        )
        self._enable_decision_makers(
            "MobsHitting",
            "TelecastMobsHitting",
            "PartyRebuff"
        )
        self._last_valid_detection = time.perf_counter()
        self._create_rotation_attributes(
            cycle=getattr(self.data, 'feature_cycle', None)
        )  # This resets the next_target procedure

    async def _failsafe_procedure(self) -> None:
        try:
            await asyncio.wait_for(
                self._rotate_until_mobs_detected(),
                timeout=self.FAILSAFE_TIMER // 2
            )
        except asyncio.TimeoutError:
            # Still no mobs.
            self._react("light")
            logger.log(
                LOG_LEVEL,
                f"No mobs detected after {self.FAILSAFE_TIMER // 2} seconds"
            )

            # Keep trying until this is cancelled by the failsafe procedure
            await self._rotate_until_mobs_detected()

    async def _rotate_until_mobs_detected(self) -> None:
        while True:
            mob_count = self.mob_count_in_img(
                self.data.current_client_img,
                self.data.current_mobs,
                debug=False
            )
            print(f"Mob count: {mob_count}")
            if mob_count >= self._alert_threshold:
                break
            await asyncio.sleep(0.5)

    def _toggle_chat_request(self) -> ActionRequest:
        return ActionRequest(
            f"{self} - Toggle Chat",
            toggle_menu,
            self.data.ign,
            priorities.ANTI_DETECTION,
            block_lower_priority=True,
            args=(self.data.handle, self.data.ign, 'Chat Toggle')
        )
