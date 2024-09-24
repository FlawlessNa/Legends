import asyncio
import multiprocessing.connection
import multiprocessing.managers
from abc import ABC, abstractmethod
from functools import cached_property

from botting.controller import release_keys
from botting.utilities import client_handler
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

    ign_finder: callable  # Method that returns the handle of a client given its IGN.

    @classmethod
    def get_handle_from_ign(cls, ign: str) -> int:
        return client_handler.get_client_handle(ign, cls.ign_finder)

    def __init__(
        self, ign: str, metadata: multiprocessing.managers.DictProxy, **kwargs
    ) -> None:
        self.ign = ign
        self.data = None
        self.metadata = metadata
        self.pipe = None
        self.barrier = None
        self.kwargs = kwargs

        self._bot: asyncio.Task | None = None
        self._tg: asyncio.TaskGroup | None = None

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: multiprocessing.managers.BarrierProxy,
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        """
        self.data = BotData(self.ign)
        self.data.create_attribute("handle", lambda: self.get_handle_from_ign(self.ign))
        self.pipe = pipe
        self.barrier = barrier

    async def start(self) -> None:
        """
        Called by the Engine to start the DecisionMakers tasks.
        Passes the TaskGroup to each DecisionMaker, such that they can define sub-tasks
        if required.
        """
        self._bot = asyncio.current_task()

        async with asyncio.TaskGroup() as tg:
            self._tg = tg
            decision_makers = self.decision_makers  # Instantiate DecisionMakers.

            # Synchronizes the start of all bots at the same time.
            await asyncio.to_thread(self.barrier.wait)

            for dm in decision_makers:
                tg.create_task(dm.start(tg), name=f"{dm}")

    def pause(self) -> None:
        """
        Pauses all DecisionMakers tasks.
        This can be overridden to provide custom behavior.
        """
        for dm_class in self._decision_makers():
            for task in asyncio.all_tasks():
                name = task.get_name()
                if 'Enabler' in name or 'Disabler' in name:
                    continue
                elif name.startswith(dm_class.__name__):
                    task.cancel()
        release_keys(['left', 'up', 'down', 'right'], self.data.handle)

    def resume(self) -> None:
        """
        Resumes the DecisionMakers tasks.
        """
        for dm in self.decision_makers:
            self._tg.create_task(dm.task(), name=f"{dm}")

    @cached_property
    def decision_makers(self) -> list[DecisionMaker]:
        """
        A list of DecisionMakers that are used to make decisions for this Bot.
        :return:
        """
        assert self.data is not None
        assert self.pipe is not None
        return [
            class_(self.metadata, self.data, self.pipe, **self.kwargs)
            for class_ in self._decision_makers()
        ]

    @abstractmethod
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        pass
