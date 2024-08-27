import logging
import royals.decision_makers as decision_makers

from botting import PARENT_LOG
from botting.core import DecisionMaker
from .royals_bot import RoyalsBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class LeechingBot(RoyalsBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            # decision_makers.TelecastMobsHitting,
            # decision_makers.Rotation,
            # decision_makers.AbilityPointDistributor,
            decision_makers.PetFood,
            # decision_makers.SoloRebuff,
            # decision_makers.PartyRebuff,
            decision_makers.InventoryManager
        ]
