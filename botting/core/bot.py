import asyncio
import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import cached_property
from typing import Any

from botting.controller import release_keys
from botting.utilities import client_handler

from .action_data import ActionRequest
from .bot_data import BotData
from .decision_maker import DecisionMaker

USER_REQUESTS_PRIORITY = 98  # Matches a user-issued request: pause comes from Discord.


class Bot(ABC):
    """
    Abstract base class to represent a Bot of any kind.
    A Bot is a container of DecisionMakers, which are cycled and called
    one at a time.

    A bot represents a single game client entity and is assigned a single
    BotData instance which it shares with all its DecisionMakers.
    """

    ign_finder: Callable[
        ..., Any
    ]  # Method that returns the handle of a client given its IGN.

    @classmethod
    def get_handle_from_ign(cls, ign: str) -> int:
        return client_handler.get_client_handle(ign, cls.ign_finder)

    def __init__(
        self, ign: str, metadata: multiprocessing.managers.DictProxy, **kwargs: object
    ) -> None:
        self.ign = ign
        # Filled in by `child_init`, inside the Engine process: a Bot is built in
        # Main Process and shipped over a pipe, and none of these three survive
        # that trip. Everything that reads them runs after `child_init`.
        self.data: BotData | None = None
        self.pipe: multiprocessing.connection.Connection | None = None
        self.barrier: threading.Barrier | None = None
        self.metadata = metadata
        self.kwargs = kwargs

        self._bot: asyncio.Task | None = None
        self._tg: asyncio.TaskGroup | None = None

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: multiprocessing.managers.BarrierProxy,  # type: ignore
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        """
        self.data = BotData(self.ign)
        self.data.set_static("handle", self.get_handle_from_ign(self.ign))
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
            assert self.barrier is not None, "child_init() must run before start()"
            await asyncio.to_thread(self.barrier.wait)

            for dm in decision_makers:
                tg.create_task(dm.start(tg), name=f"{dm}")

    def pause(self) -> None:
        """
        Pauses all DecisionMakers tasks.
        This can be overridden to provide custom behavior.
        Runs inside the Engine process, which may not send input, so the movement keys
        are dropped through an ActionRequest executed in Main Process instead.
        """
        for dm_class in self._decision_makers():
            for task in asyncio.all_tasks():
                name = task.get_name()
                if "Enabler" in name or "Disabler" in name:
                    continue
                elif name.startswith(dm_class.__name__):
                    task.cancel()
        assert self.pipe is not None
        assert self.data is not None
        self.pipe.send(
            ActionRequest(
                f"Releasing movement keys - {self.ign}",
                self._release_movement_keys,
                ign=self.ign,
                priority=USER_REQUESTS_PRIORITY,
                requeue_if_not_scheduled=False,
                cancels_itself=True,
                args=(self.data.handle,),
            )
        )

    @staticmethod
    async def _release_movement_keys(handle: int) -> None:
        """
        Called in Main Process as an ActionRequest procedure.
        """
        release_keys(["left", "up", "down", "right"], handle)

    def resume(self) -> None:
        """
        Resumes the DecisionMakers tasks.
        """
        assert self._tg is not None, "start() must run before resume()"
        for dm in self.decision_makers:
            task = self._tg.create_task(dm.task(), name=f"{dm}")
            dm.decision_task = task

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
