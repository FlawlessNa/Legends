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
    TimeBasedFailsafeMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class AbilityPointDistributor(
    DecisionMaker,
):
    CONFIG_KEY = "Ability Menu"
    _throttle = 30.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        movements_duration: float = 1.0,
        static_position_threshold: float = 7.5,
        no_path_threshold: float = 5.0,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._ap_menu_key = controller.key_binds(self.data.ign)[self.CONFIG_KEY]

    async def _decide(self) -> None:
        self._failsafe_checks()  # Check each time, no need to wait for lock

        # Only send standard request when lock is acquired, otherwise wait for lock
        acquired = self.lock.acquire(blocking=False)
        if acquired:
            logger.log(LOG_LEVEL, f"{self} is deciding.")
            self.data.update_attribute("next_target")
            self.data.update_attribute("action")
            if self.data.action is not None:
                print(self.data.action.duration)
                self.pipe.send(self._request(self.data.action))
            else:
                self.lock.release()

    def _request(self, inputs: controller.KeyboardInputWrapper) -> ActionRequest:
        return ActionRequest(
            f"{self}",
            inputs.send,
            ign=self.data.ign,
            requeue_if_not_scheduled=True,
            callbacks=[self.lock.release],
        )

    def _failsafe_request(self, disc_msg: str = None) -> ActionRequest:
        alert = (
            DiscordRequest(disc_msg, self.data.current_client_img) if disc_msg else None
        )

        return ActionRequest(
            f"{self} - Failsafe",
            random_jump(
                self.data.handle, controller.key_binds(self.data.ign)["jump"]
            ).send,
            ign=self.data.ign,
            priority=10,
            requeue_if_not_scheduled=True,
            block_lower_priority=True,
            cancel_tasks=[f"{self}"],
            discord_request=alert,
        )
