import asyncio
import multiprocessing.managers
from abc import ABC, abstractmethod
from functools import cached_property

from .bot_data import BotData
from .decision_maker import DecisionMaker


class Bot(ABC):
    """
    Abstract base class to represent a Bot of any kind.
    A Bot is a container of DecisionMakers, which are cycled and called
    one at a time.

    A bot represents a single game client entity and is assigned a single
    BotData instance which it shares with all its DecisionMakers.
    """

    def __init__(self, ign: str, metadata: multiprocessing.managers.DictProxy) -> None:
        self.ign = ign
        self.data = None
        self.metadata = metadata
        # self.metadata["Blockers"][ign] = {
        #     val: dict() for val in DecisionMaker.__annotations__["_type"].__args__
        # }

    def child_init(self) -> None:
        """
        Called by the Engine to create Bot within Child process.
        """
        self.data = BotData(self.ign)

    async def start(self) -> None:
        """
        Called by the Engine to start the DecisionMakers tasks.
        """
        async with asyncio.TaskGroup() as tg:
            for decision_maker in self.decision_makers:
                tg.create_task(
                    decision_maker.start(),
                    name=f'{self.ign} - {decision_maker}'
                )

    @cached_property
    @abstractmethod
    def decision_makers(self) -> list[DecisionMaker]:
        """
        A list of DecisionMakers that are used to make decisions for this Bot.
        :return:
        """
        pass
