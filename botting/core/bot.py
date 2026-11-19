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
from .data_keys import Provider, Providers, resolve_providers
from .decision_maker import DecisionMaker
from .proxy_factory import ProxyFactory
from .replies import RepliesProvider
from .signals import SignalBoard, check_signals
from .supervisor import Supervisor, resolve_cancels, resolve_pauses
from .window import WindowProvider

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
        #: Runs every DecisionMaker's loops. Built by `assemble`, once the
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

        Makes the Bot's data and its Providers, and builds the engine's
        Bot-level ones: `WindowProvider`, with the handle `find_handle` finds
        now, and `RepliesProvider`, the replies switch, on. A game layer adds
        its own Bot-level Providers after this, from what it finds and checks
        at start (`Providers.add`).
        """
        self.data = BotData(self.ign)
        self.pipe = pipe
        self.barrier = barrier
        providers = self._make_providers(self.data, pipe)
        providers.add(WindowProvider, handle=self.find_handle())
        providers.add(RepliesProvider)

    @property
    def providers(self) -> list[Provider]:
        """Every Provider built for this Bot, in the order they were set up."""
        if self.data is None or self.data.providers is None:
            return []
        return list(self.data.providers)

    def _providers(self) -> Providers:
        """
        This Bot's Providers: `child_init`'s, or, for a Bot whose data was made
        without it, made now.
        """
        assert self.data is not None, "the Bot's data is made before its Providers"
        assert self.pipe is not None, "the Bot's pipe is set before its Providers"
        if self.data.providers is None:
            return self._make_providers(self.data, self.pipe)
        return self.data.providers

    def _make_providers(
        self, data: BotData, pipe: multiprocessing.connection.Connection
    ) -> Providers:
        """This Bot's Providers, attached to `data`, with nothing built yet."""
        return Providers(
            data,
            pipe,
            ProxyFactory(self.metadata),
            self.kwargs,
            SignalBoard(data.clock),
        )

    async def start(self) -> None:
        """
        Called by the Engine: assemble the Bot, then run its DecisionMakers.

        Assembly happens before the start barrier, so a Bot wired wrong is
        refused before any bot starts. The Supervisor then runs the
        DecisionMakers' loops until the Bot ends.
        :raises StartupRefused: as `assemble` does.
        """
        self._bot = asyncio.current_task()
        self.assemble()

        # Synchronizes the start of all bots at the same time.
        assert self.barrier is not None, "child_init() must run before start()"
        await asyncio.to_thread(self.barrier.wait)

        assert self.supervisor is not None, "assemble() builds the Supervisor"
        await self.supervisor.run()

    def assemble(self) -> None:
        """
        Build what the DecisionMakers declare, then the DecisionMakers, and hand
        them to a Supervisor. `start` calls it before the start barrier:

        1. the class-level declarations are resolved, with nothing built: the
           Pauses, the classes whose Actions are cancelled, the Providers of
           every key read in the order to build them, and the Signals awaited;
        2. the Providers not built yet are built, then set up, in that order
           (the Bot-level ones were, by `child_init`);
        3. the DecisionMakers are built, then set up;
        4. the Supervisor takes them.
        :raises StartupRefused: a declaration resolves to nothing, two keys share
            a name, the Providers form a cycle, a Signal is awaited that nothing
            announces, a key is read whose Bot-level Provider this Bot did not
            build, or a Provider registers less than it provides.
        """
        assert self.data is not None, "child_init() must run before assemble()"
        assert self.pipe is not None, "child_init() must run before assemble()"

        classes = self._decision_makers()
        declared_pauses = resolve_pauses(classes)
        resolve_cancels(classes)
        order = resolve_providers(classes)
        check_signals(classes, order)

        providers = self._providers()
        providers.build(order)
        for decision_maker in self.decision_makers:
            decision_maker._signals = providers.signals  # pyright: ignore[reportPrivateUsage] - assembly wires it
        for decision_maker in self.decision_makers:
            decision_maker.setup()
        self.supervisor = Supervisor(self.ign, self.decision_makers, declared_pauses)

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
        Discord `RESUME`: release every user-held Pause, those a DecisionMaker
        took with `pause_for_user` included (`ChatReplies`, on a GM's line). A
        Pause a DecisionMaker holds in a block stays held until the block exits.
        """
        if self.supervisor is None:
            logger.warning("%s is not running yet: there is nothing to resume.", self)
            return
        self.supervisor.resume_for_user()

    def replies(self, on: bool, source: str = "discord_replies") -> None:
        """
        Stops (``on=False``) or hands back the automatic replies of this Bot.
        Switches `REPLIES_ON`, which the DecisionMaker that replies reads before
        each reply, and reports the switch.
        :param on: Whether automatic replies are on.
        :param source: Which command did it, for the report.
        """
        assert self.data is not None, "child_init() makes the Bot's data"
        providers = self.data.providers
        assert providers is not None, "child_init() builds the replies switch"
        providers.get(RepliesProvider).switch(on)
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
