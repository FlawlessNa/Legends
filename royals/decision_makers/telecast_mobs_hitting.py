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

    def _teleport_in_upcoming_action(self) -> bool:
        teleport_key = self._teleport_skill.key_bind(self.data.ign)
        if self.data.action is not None and teleport_key in self.data.action.keys:
            return True
        return False

    def _hit_mobs(self, *args, **kwargs) -> ActionRequest:
        """
        # TODO - Cancel current rotation, retrieve current action and overwrite teleports
        inputs with telecast inputs. Use a ultimate_skill.animation_time action duration.
        :param direction:
        :return:
        """
        if self._teleport_in_upcoming_action():
            inputs = self.data.action
            logger.log(LOG_LEVEL, f"{self} is about to Telecast.")
            return ActionRequest(
                f"{self}",
                telecast(
                    inputs,
                    self._teleport_skill.key_bind(self.data.ign),
                    self.training_skill.key_bind(self.data.ign)
                ).send,
                ign=self.data.ign,
                priority=2,
                cancel_tasks=[f"Rotation({self.data.ign})"],
                block_lower_priority=True,
                callbacks=[self.lock.release]
            )
        else:
            return super()._hit_mobs(direction=None)

