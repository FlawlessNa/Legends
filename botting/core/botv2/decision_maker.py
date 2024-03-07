from abc import ABC, abstractmethod
from typing import Literal

from .bot_data import BotData
from .action_data import ActionData


class DecisionMaker(ABC):
    """
    Abstract base class to represent a decision maker of any kind.
    Each Bot consists of one or more DecisionMaker, which are cycled and called
    one at a time.
    When called, a DecisionMaker may return an ActionData container,
    which will be sent to the Main Process to be executed there.

    DecisionMakers may additionally define Multiprocessing Synchronization Primitives
    that will be shared with other instances of the same DecisionMaker class.
    The other instances do not necessarily live in the same Process, as this depends
    on how each Monitor are assigned to their Engines.
    """

    generator_type: Literal["Rotation", "AntiDetection", "Maintenance"]

    def __init__(self, data: BotData) -> None:
        self.data = data

    def block_others(self):
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def _call(self, *args, **kwargs) -> ActionData | None:
        pass

    def __call__(self, *args, **kwargs) -> ActionData | None:
        pass
