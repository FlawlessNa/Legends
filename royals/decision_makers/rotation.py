import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from royals.actions.movements_v2 import random_jump
from .mixins import (
    MinimapAttributesMixin,
    MovementsMixin,
    NextTargetMixin,
    TimeBasedFailsafeMixin
)
logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class Rotation(
    DecisionMaker,
    NextTargetMixin,
    MinimapAttributesMixin,
    MovementsMixin,
    TimeBasedFailsafeMixin
):
    # TODO - Implement logic to continuously check if character strayed too far from
    #  path to cancel current movements
    _throttle = 0.1
    STATIC_POS_KILL_SWITCH = 20.0
    NO_PATH_KILL_SWITCH = 20.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        movements_duration: float = 0.75,
        static_position_threshold: float = 7.5,
        no_path_threshold: float = 5.0,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get("Teleport")
        self.lock = self.request_proxy(self.metadata, f"{self}", "Lock")

        # Minimap attributes
        self._create_minimap_attributes()
        self.data.current_minimap.generate_grid_template(
            True if self._teleport_skill is not None else False
        )

        # Rotation attributes
        self._create_rotation_attributes()
        self._create_pathing_attributes(
            self.data.ign,
            self.data.handle,
            self._teleport_skill,
            self.data.current_minimap,
            movements_duration,
        )

        # Fail safes
        self._sentinels = []
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=static_position_threshold,
            response=self._failsafe_request()
        )
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=2 * static_position_threshold,
            response=self._failsafe_request(f"{self.data.ign} is stuck.")
        )
        self._create_time_based_sentinel(
            attribute="current_minimap_position",
            method=self.data.get_time_since_last_value_change,
            threshold=self.STATIC_POS_KILL_SWITCH,
            response=...  # TODO - Kill switch
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=no_path_threshold,
            response=self._failsafe_request()
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=2 * no_path_threshold,
            response=self._failsafe_request(f"{self.data.ign} has no path.")
        )
        self._create_time_based_sentinel(
            attribute="path",
            method=self.data.get_time_since_last_valid_update,
            threshold=self.NO_PATH_KILL_SWITCH,
            response=...  # TODO - Kill switch
        )

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
        return ActionRequest(
            f"{self}",
            inputs.send,
            ign=self.data.ign,
            requeue_if_not_scheduled=True,
            callbacks=[self.lock.release]
        )

    def _failsafe_request(
        self, disc_msg: str = None
    ) -> ActionRequest:

        alert = DiscordRequest(disc_msg) if disc_msg else None
        return ActionRequest(
            f"{self} - Failsafe",
            random_jump(
                self.data.handle, controller.key_binds(self.data.ign)['jump']
            ).send,
            ign=self.data.ign,
            priority=10,
            requeue_if_not_scheduled=True,
            block_lower_priority=True,
            cancel_tasks=[f"{self}"],
            discord_request=alert,
        )
