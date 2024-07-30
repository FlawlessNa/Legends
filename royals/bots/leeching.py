import logging
import royals.decision_makers as decision_makers

from botting import PARENT_LOG
from .royals_bot import RoyalsBot
from botting.core.botv2.decision_maker import DecisionMaker

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class LeechingBot(RoyalsBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            decision_makers.MobsHitting,
            # decision_makers.TelecastRotation,
        ]
