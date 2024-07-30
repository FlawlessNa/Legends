import asyncio
import logging
from botting import PARENT_LOG
from .royals_bot import RoyalsBot
from botting.core.botv2.decision_maker import DecisionMaker

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET


class TestMaker(DecisionMaker):
    def __repr__(self) -> str:
        return "TestMaker"

    async def _decide(self) -> None:
        import random

        logger.log(LOG_LEVEL, f"{self} is deciding.")
        await asyncio.sleep(random.uniform(10, 20))


class TestBot(RoyalsBot):
    def _decision_makers(self) -> list[DecisionMaker]:
        return [
            TestMaker(self.metadata, self.data, self.pipe),
        ]
