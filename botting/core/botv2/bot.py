import multiprocessing.managers
from abc import ABC, abstractmethod

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
        self.data = BotData(ign)
        self.metadata = metadata
        self.metadata["Blockers"][ign] = {
            val: dict() for val in DecisionMaker.__annotations__["_type"].__args__
        }

    @property
    @abstractmethod
    def decision_makers(self) -> list[DecisionMaker]:
        """
        TODO - Implement these as cached_property?
        A list of DecisionMakers that are used to make decisions for this Bot.
        :return:
        """
        pass
