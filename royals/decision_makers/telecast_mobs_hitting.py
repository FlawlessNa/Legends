import asyncio
import logging
from botting import PARENT_LOG
from botting.core import ActionRequest
from .mobs_hitting import MobsHitting
from royals.actions.movements_v2 import telecast

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


class TelecastMobsHitting(MobsHitting):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._teleport_skill = self.data.character.skills["Teleport"]
        self._teleport_key = self._teleport_skill.key_bind(self.data.ign)

    def _teleport_in_upcoming_action(self) -> bool:
        if self.data.action is not None and self._teleport_key in self.data.action.keys:
            return True
        return False

    def _hit_mobs(self, *args, **kwargs) -> ActionRequest:
        """
        :param direction:
        :return:
        """
        if self._teleport_in_upcoming_action():
            inputs = self.data.action
            logger.log(LOG_LEVEL, f"{self} is about to Telecast.")
            telecast_action = telecast(
                inputs,
                self.data.ign,
                self._teleport_skill.key_bind(self.data.ign),
                self.training_skill,
            )
            asyncio.get_running_loop().call_later(
                self.training_skill.animation_time + 0.1, self.lock.release
            )
            return ActionRequest(
                f"{self}",
                telecast_action.send,
                ign=self.data.ign,
                priority=2,
                cancel_tasks=[f"Rotation({self.data.ign})"],
                block_lower_priority=True,
                cancels_itself=True,
                # callbacks=[self.lock.release],
            )
        else:
            return super()._hit_mobs(direction=None)
