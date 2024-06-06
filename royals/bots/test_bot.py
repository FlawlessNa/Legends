from functools import cached_property
from botting.core.botv2.bot import Bot
from botting.core.botv2.decision_maker import DecisionMaker

from royals.decision_makers import TelecastRotation


class TestBot(Bot):
    @cached_property
    def decision_makers(self) -> list[DecisionMaker]:
        return [
            TelecastRotation(...)
            ]
