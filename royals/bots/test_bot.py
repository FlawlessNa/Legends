import asyncio
import logging
from functools import cached_property
from botting import PARENT_LOG
from botting.core.botv2.bot import Bot
from botting.core.botv2.decision_maker import DecisionMaker

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')
LOG_LEVEL = logging.NOTSET


class TestMaker(DecisionMaker):

    def __repr__(self) -> str:
        return 'TestMaker'

    async def _decide(self) -> None:
        import random
        import multiprocessing
        logger.log(LOG_LEVEL, f'{self} is deciding.')
        for task in asyncio.all_tasks():
            print(f'Process {multiprocessing.current_process().name} - {task}')
        await asyncio.sleep(random.uniform(10, 20))
        raise Exception('Test Exception')


class TestBot(Bot):
    @cached_property
    def decision_makers(self) -> list[DecisionMaker]:
        return [
            TestMaker(self.metadata, self.data),
            ]
