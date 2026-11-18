import logging

from botting import PARENT_LOG
from botting.core import DecisionMaker
from maple import decision_makers

from .maple_bot import MapleBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class TrainingBot(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            decision_makers.MobsHitting,
            decision_makers.Rotation,
            # decision_makers.AbilityPointDistributor,
            decision_makers.PetFood,
            decision_makers.SoloRebuff,
            # decision_makers.SpeedPill,
            decision_makers.CheckMobsStillSpawn,
            decision_makers.CheckStillInMap,
            decision_makers.ChatReplies,
        ]
