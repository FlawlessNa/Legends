import logging
import royals.decision_makers as decision_makers

from botting import PARENT_LOG
from botting.core.botv2.bot import Bot
from botting.core.botv2.decision_maker import DecisionMaker

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')
LOG_LEVEL = logging.NOTSET


class LeechingBot(Bot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [
            decision_makers.TelecastMobsHitting,
            # decision_makers.TelecastRotation,
        ]
