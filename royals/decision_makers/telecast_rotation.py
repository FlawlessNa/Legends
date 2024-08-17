import multiprocessing.connection
import multiprocessing.managers

from botting import controller
from botting.core import ActionRequest, BotData, DecisionMaker
from .mobs_hitting import MobsHitting


class TelecastRotation(MobsHitting):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._teleport_skill = self.data.character.skills["Teleport"]

    def _teleport_in_upcoming_action(self) -> bool:
        action: controller.KeyboardInputWrapper = self.data.action
        teleport_key = self._teleport_skill.key_bind(self.data.ign)
        if teleport_key in self.data.action.keys:
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
            print("Telecasting rotation")
            return ActionRequest(
                f"{self}",
                inputs.send,
                ign=self.data.ign,
                priority=2,
                cancel_tasks=[f"Rotation({self.data.ign})"],
                block_lower_priority=True,
                callbacks=[self.lock.release]
            )
        else:
            return super()._hit_mobs(direction=None)

