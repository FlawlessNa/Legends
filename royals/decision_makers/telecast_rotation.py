from .mobs_hitting import MobsHitting
from botting.core import ActionRequest, BotData, DecisionMaker


class TelecastRotation(MobsHitting):

    async def _hit_mobs(self, *args, **kwargs) -> ActionRequest:
        """
        # TODO - Cancel current rotation, retrieve current action and overwrite teleports
        inputs with telecast inputs. Use a ultimate_skill.animation_time action duration.
        :param direction:
        :return:
        """
        pass
