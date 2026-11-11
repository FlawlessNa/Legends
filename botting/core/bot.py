import asyncio
import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC, abstractmethod
from functools import cached_property

from botting.controller import release_keys

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
        barrier: multiprocessing.managers.BarrierProxy,  # pyright: ignore[reportAttributeAccessIssue]
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        """
        self.data = BotData(self.ign)
        self.data.set_static("handle", self.find_handle())
        self.data.set_static("replies_on", True)
        # What a DecisionMaker that stops the others' (ChatReplies, on a GM) names.
        self.data.set_static(
            "decision_maker_names",
            tuple(class_.__name__ for class_ in self._decision_makers()),
        )
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

        Each DecisionMaker's ``on_resume`` hook runs first: one that disabled others
        and gives them back on RESUME (``ChatReplies``, after a GM) enables them
        there, and their enablers restart them. Every other DecisionMaker whose task
        isn't running is restarted, as ``pause`` left it, and counts as enabled
        again (``DecisionMaker.restart``), so a later enable finds it running. One
        still running is left alone, so a RESUME with no PAUSE before it never runs
        a loop twice.
        """
        assert self._tg is not None, "start() must run before resume()"
        enabled = {name for dm in self.decision_makers for name in dm.on_resume()}
        for dm in self.decision_makers:
            if type(dm).__name__ not in enabled:
                dm.restart(self._tg)

    def replies(self, on: bool, source: str = "discord_replies") -> None:
        """
        Stops (``on=False``) or hands back the automatic replies of this Bot.
        Sets the ``replies_on`` static of its BotData, which the DecisionMaker
        that replies reads before each reply, and reports the switch.
        :param on: Whether automatic replies are on.
        :param source: Which command did it, for the report.
        """
        assert self.data is not None, "child_init() must run before replies()"
        self.data.set_static("replies_on", on)
        self._replies_toggled(on, source)

    def takeover(self) -> None:
        """The maintainer writes for this Bot: its automatic replies stop."""
        self.replies(False, source="discord_write")

    def _replies_toggled(self, on: bool, source: str) -> None:
        """
        Called once `replies` has switched. A game layer overrides it to emit its
        own Event Type: the engine knows no game's events.
        """

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
