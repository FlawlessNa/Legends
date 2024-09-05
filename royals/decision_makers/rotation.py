import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from functools import partial
from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from royals.actions.movements_v2 import random_jump
from royals.actions import priorities
from .mixins import (
    MinimapAttributesMixin,
    MovementsMixin,
    NextTargetMixin,
    TimeBasedFailsafeMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class Rotation(
    NextTargetMixin,
    MinimapAttributesMixin,
    MovementsMixin,
    TimeBasedFailsafeMixin,
    DecisionMaker,
):
    # TODO - Implement logic to continuously check if character strayed too far from
    #  path to cancel current movements
    # TODO - improved failsafe reactions, including writing in chat after 2x or 3x
    _throttle = 0.1
    STATIC_POS_KILL_SWITCH = 30.0
    NO_PATH_KILL_SWITCH = 30.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        movements_duration: float = 1.0,
        static_position_threshold: float = 10.0,
        no_path_threshold: float = 10.0,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get("Teleport")
        self.lock = self.request_proxy(self.metadata, f"{self}", "Lock")

        # Minimap attributes
        self._create_minimap_attributes()

        # Rotation attributes
        self._create_rotation_attributes()
        self._create_pathing_attributes(movements_duration)

        # Fail safes
        self._sentinels = []
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=static_position_threshold,
            response=self._failsafe_request(),
        )
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=2 * static_position_threshold,
            response=self._failsafe_request(f"{self.data.ign} is stuck."),
        )
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=self.STATIC_POS_KILL_SWITCH,
            response=...,  # TODO - Trigger Pause mechanism until resumed by user
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=no_path_threshold,
            response=self._failsafe_request(),
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=2 * no_path_threshold,
            response=self._failsafe_request(f"{self.data.ign} has no path."),
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=self.NO_PATH_KILL_SWITCH,
            response=...,  # TODO - Trigger Pause mechanism until resumed by user
        )
        self._sentinel_starts_at = time.perf_counter() + 60.0

    async def _task(self, *args, **kwargs) -> None:
        self._sentinel_starts_at = time.perf_counter() + 10.0
        await super()._task(*args, **kwargs)

    async def _decide(self) -> None:
        self._failsafe_checks()  # Check each time, no need to wait for lock

        # Only send standard request when lock is acquired, otherwise wait for lock
        acquired = self.lock.acquire(blocking=False)
        if acquired:
            logger.log(LOG_LEVEL, f"{self} is deciding.")
            self.data.update_attribute("next_target")
            self.data.update_attribute("action")
            if self.data.action is not None:
                self.pipe.send(self._request(self.data.action))
            else:
                self.lock.release()

    def _request(self, inputs: controller.KeyboardInputWrapper) -> ActionRequest:
        # TODO - Could switch to requeue=False while ensuring that the lock is released.
        # This is because Telecasting will move the character, and the next action should
        # be based on the new position.
        return ActionRequest(
            f"{self}",
            inputs.send,
            ign=self.data.ign,
            requeue_if_not_scheduled=True,
            callbacks=[self.lock.release],
            cancel_callback=partial(self._release_left_right, self.data.handle),
        )

    @staticmethod
    def _release_left_right(handle: int, fut: asyncio.Future) -> None:
        if not fut.cancelled():
            return
        held = list(
            filter(
                lambda i: i in ["left", "right"],
                controller.get_held_movement_keys(handle),
            )
        )
        if held:
            controller.release_keys(held, handle)

    def _failsafe_request(self, disc_msg: str = None) -> ActionRequest:
        alert = (
            DiscordRequest(disc_msg, self.data.current_client_img) if disc_msg else None
        )

        return ActionRequest(
            f"{self} - Failsafe",
            self._wait_and_random_jump,
            ign=self.data.ign,
            priority=priorities.FAILSAFE,
            requeue_if_not_scheduled=True,
            block_lower_priority=True,
            cancels_itself=True,
            cancel_tasks=[f"{self}"],
            discord_request=alert,
            args=(self.data.handle, controller.key_binds(self.data.ign)["jump"]),
        )

    @staticmethod
    async def _wait_and_random_jump(handle: int, jump_key: str) -> None:
        await asyncio.sleep(3.0)
        await random_jump(handle, jump_key).send()
