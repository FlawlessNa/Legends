import logging
import maple.decision_makers as decision_makers

from botting import PARENT_LOG
from botting.core import DecisionMaker
from .maple_bot import MapleBot

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class LeechMuleWithBuffs(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            decision_makers.AbilityPointDistributor,
            decision_makers.PetFood,
            decision_makers.ResetIdleSafeguard,
            decision_makers.PartyRebuff,
        ]


class LeechMuleWithoutBuffs(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            decision_makers.AbilityPointDistributor,
            # decision_makers.PartyRebuff,
            decision_makers.EnsureSafeSpot,
        ]
