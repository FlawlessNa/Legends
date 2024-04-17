from botting.core.botv2.bot import Bot
from botting.core.botv2.decision_maker import DecisionMaker


class TestBot(Bot):
    @property
    def decision_makers(self) -> list[DecisionMaker]:
        pass
