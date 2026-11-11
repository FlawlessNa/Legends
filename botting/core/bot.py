import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC, abstractmethod
from functools import cached_property

from botting.controller import release_keys

from .action_data import ActionRequest
from .bot_data import BotData
from .decision_maker import DecisionMaker
from .supervisor import Supervisor, resolve_pauses

logger = logging.getLogger(__name__)

USER_REQUESTS_PRIORITY = 98  # Matches a user-issued request: pause comes from Discord.


class Bot(ABC):
    """
    Abstract base class to represent a Bot of any kind.
    A Bot is a container of DecisionMakers, whose decision loops its Supervisor
    runs concurrently.

    A bot represents a single game client entity and is assigned a single
    BotData instance which it shares with all its DecisionMakers.
    """

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
        #: Runs every DecisionMaker's loops. Built by `start`, once the
        #: DecisionMakers are.
        self.supervisor: Supervisor | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.ign})"

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: multiprocessing.managers.BarrierProxy,  # pyright: ignore[reportAttributeAccessIssue]
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        """
        self.data = BotData(self.ign)
        self.data.set_static("handle", self.find_handle())
        self.pipe = pipe
        self.barrier = barrier

    async def start(self) -> None:
        """
        Called by the Engine: assemble the Bot, then run its DecisionMakers.

        Assembly happens before the start barrier, so a Bot wired wrong is
        refused before any bot starts: the class-level declarations are resolved
        first, with no DecisionMaker built, then the DecisionMakers are built and
        handed to the Supervisor, which runs their loops until the Bot ends.
        :raises StartupRefused: a declaration resolves to nothing.
        """
        self._bot = asyncio.current_task()

        declared_pauses = resolve_pauses(self._decision_makers())
        self.supervisor = Supervisor(self.ign, self.decision_makers, declared_pauses)

        # Synchronizes the start of all bots at the same time.
        assert self.barrier is not None, "child_init() must run before start()"
        await asyncio.to_thread(self.barrier.wait)

        await self.supervisor.run()

    def pause(self) -> None:
        """
        Discord `PAUSE`: a Pause held by the user on every DecisionMaker, which
        only `resume` releases, and the movement keys released.

        Runs inside the Engine process, which may not send input, so the movement
        keys are dropped through an ActionRequest executed in Main Process instead.
        """
        if self.supervisor is None:
            logger.warning("%s is not running yet: there is nothing to pause.", self)
        else:
            self.supervisor.pause_for_user(reason="Discord PAUSE")
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
        Discord `RESUME`: release every user-held Pause, and every legacy shim
        Pause, as `RESUME` has always restarted every DecisionMaker. A Pause a
        DecisionMaker holds in a block stays held until the block exits.
        """
        if self.supervisor is None:
            logger.warning("%s is not running yet: there is nothing to resume.", self)
            return
        self.supervisor.resume_for_user()

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
    def find_handle(self) -> int:
        """
        The handle of this Bot's game window, looked up now. Input goes to it, so
        a game layer finds it by what the window is, never by guessing.
        """

    @abstractmethod
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        pass
