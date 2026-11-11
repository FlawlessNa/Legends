import asyncio
import contextlib
import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import Any, ClassVar, NamedTuple

from botting.logging_config import producer_logger_name
from botting.telemetry import emit_event
from botting.telemetry_events import (
    DECISION_DISABLED,
    DECISION_ENABLED,
    DECISION_PAUSED,
    DECISION_RESUMED,
    DecisionGatePayload,
)

from .action_data import ActionRequest, ActionWithValidation
from .bot_data import BotData
from .data_keys import Key, KeyNotDeclared
from .proxy_factory import ProxyFactory
from .signals import Announcement, Signal, SignalBoard
from .supervisor import USER, Pause, PauseKind, Supervisor

logger = logging.getLogger(__name__)

#: The priority of the request a `cancel_actions=True` Pause sends. It must be
#: scheduled to cancel anything, so it outranks every blocker a game layer sets
#: short of a kill switch; it blocks nothing itself.
CANCEL_ACTIONS_PRIORITY = 98


def action_name(cls: type, ign: str) -> str:
    """
    The identifier `cls`'s Actions carry for the bot `ign`: what Main Process
    names their tasks, and so what `ActionRequest.cancel_tasks` names to cancel
    them. `DecisionMaker.__repr__` is built from it, so the two cannot drift.

    A plain function, so Main Process code that names a DecisionMaker's Actions
    without holding one (the Discord parser) uses it too.
    """
    return f"{cls.__name__}({ign})"


class DecisionLoop(NamedTuple):
    """One decision loop of a DecisionMaker: what it is called, and one decision."""

    #: The task name the loop runs and logs under.
    name: str
    #: One decision. The loop mints a fresh Correlation ID before each call.
    decide: Callable[[], Awaitable[None]]


class PauseNotDeclared(Exception):
    """A DecisionMaker paused a class its `pauses` declaration does not name."""


async def _cancel_only() -> None:
    """
    The procedure of a `cancel_actions=True` Pause's request: its work is the
    `cancel_tasks` Main Process acts on before scheduling it, so it does nothing.
    """


class DecisionMaker(ABC):
    """
    Abstract base class to represent a decision maker of any kind.
    Each Bot consists of one or more DecisionMaker, whose decision loops its
    Supervisor runs as asyncio tasks, concurrently.
    When called, a DecisionMaker may return an ActionRequest container,
    which will be sent to the Main Process to be executed there.
    """

    _throttle: float | None = None

    #: The DecisionMaker classes this one may pause. An entry is the class, or its
    #: dotted path ("package.module.ClassName") where importing the class would
    #: create a cycle; assembly resolves it, and refuses the start when it
    #: resolves to nothing. Pausing a class not named here raises.
    pauses: ClassVar[tuple[type[DecisionMaker] | str, ...]] = ()

    #: The Data Keys this DecisionMaker reads with `read`. Assembly builds and
    #: sets up their Providers before any DecisionMaker is built.
    reads: ClassVar[tuple[Key[Any], ...]] = ()
    #: The Data Keys this DecisionMaker only peeks at with `peek`: their last
    #: known value, never refreshed. Observing a key never builds its Provider.
    observes: ClassVar[tuple[Key[Any], ...]] = ()
    #: The Signals this DecisionMaker announces, with `announce`.
    announces: ClassVar[tuple[Signal[Any], ...]] = ()
    #: The Signals this DecisionMaker waits for, with `wait_for`. Assembly refuses
    #: the start when nothing in the Bot announces one.
    awaits: ClassVar[tuple[Signal[Any], ...]] = ()

    #: Set by whichever subclass or mixin needs one - `_validate_request_async`
    #: falls back to it when a caller passes no condition of its own.
    _condition: threading.Condition

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        self.metadata = metadata
        self.data = data
        self.pipe = pipe
        self._proxies = ProxyFactory(metadata)

        #: Set by the Supervisor that runs this DecisionMaker's loops, once the
        #: Bot is assembled. None for a DecisionMaker built on its own.
        self._supervisor: Supervisor | None = None
        #: Set by assembly before `setup()`. None for a DecisionMaker built alone.
        self._signals: SignalBoard | None = None

        # Identifies the current _decide() call. Minted by the decision loop, read by
        # send() and by any Producer that must carry the id into a procedure itself.
        # Set by the base class only - subclasses never assign it. None until the
        # first _decide().
        self.correlation_id: str | None = None

        # Logger name this DecisionMaker's Telemetry Records are attributed to,
        # following whichever convention its own module follows. Getting this
        # right is what keeps a record attributable to the subsystem that
        # produced it.
        self._logger_name = producer_logger_name(type(self).__module__)

    def __repr__(self) -> str:
        return action_name(type(self), self.data.ign)

    @abstractmethod
    async def _decide(self) -> None:
        pass

    def setup(self) -> None:
        """
        This DecisionMaker's one-time I/O, which `__init__` must not do. Called
        once by assembly, after every Provider is set up and every DecisionMaker
        built, before any loop starts. An unported DecisionMaker, which still does
        its I/O in `__init__`, leaves it empty.
        """

    # --- Data Keys ----------------------------------------------------------------

    def read[T](self, key: Key[T]) -> T:
        """
        `key`'s value, refreshed first when its threshold has passed.
        :raises KeyNotDeclared: `key` is not in this class's `reads`.
        """
        if key not in type(self).reads:
            raise KeyNotDeclared(
                f"{self} read {key.name!r}, which {type(self).__name__}.reads does "
                "not declare."
            )
        return self.data.read(key)

    def peek[T](self, key: Key[T]) -> T | None:
        """
        `key`'s last known value, without refreshing it, or None when there is
        none: its Provider may not be built, or not have read anything yet.
        :raises KeyNotDeclared: `key` is in neither this class's `reads` nor its
            `observes`.
        """
        if key not in type(self).reads and key not in type(self).observes:
            raise KeyNotDeclared(
                f"{self} peeked at {key.name!r}, which neither "
                f"{type(self).__name__}.reads nor .observes declares."
            )
        return self.data.peek(key)

    # --- Signals ------------------------------------------------------------------

    def announce[T](self, signal: Signal[T], payload: T) -> None:
        """
        Announce `signal`, waking every DecisionMaker waiting for it.
        :raises SignalNotDeclared: `signal` is not in this class's `announces`.
        """
        self._board().announce(signal, payload, by=self)

    async def wait_for[T](self, signal: Signal[T]) -> T:
        """
        The payload of the next announcement of `signal` after this call.
        :raises SignalNotDeclared: `signal` is not in this class's `awaits`.
        """
        return await self._board().wait_for(signal, by=self)

    def last[T](self, signal: Signal[T]) -> Announcement[T] | None:
        """
        The latest announcement of `signal`: its payload and when it came, on the
        Bot's clock. None when it has not been announced yet.
        :raises SignalNotDeclared: `signal` is in neither `announces` nor `awaits`.
        """
        return self._board().last(signal, by=self)

    def _board(self) -> SignalBoard:
        if self._signals is None:
            raise RuntimeError(
                f"{self} has no Signals: they exist only once its Bot has started."
            )
        return self._signals

    # --- what the Supervisor runs -----------------------------------------------

    def loops(self) -> Sequence[DecisionLoop]:
        """
        This DecisionMaker's decision loops, asked for at every start and restart.

        One by default, deciding with `_decide`. A DecisionMaker that needs
        several (one per buff, each on its own clock) overrides this, and only
        this: the Supervisor runs them, cancels them and restarts them together.
        """
        return (DecisionLoop(repr(self), self._decide),)

    def on_start(self) -> None:
        """
        Called by the Supervisor before every start and restart of this
        DecisionMaker's loops: the first start, and every resume from a Pause.
        Resets whatever a stopped run may have left behind.
        """

    def on_stop(self) -> None:
        """
        Called by the Supervisor once this DecisionMaker's loops have stopped,
        whatever stopped them: a Pause, the Bot ending, or a loop that raised.
        """

    def send(self, request: ActionRequest) -> None:
        """
        Sole chokepoint through which a DecisionMaker reaches the Main Process.
        Stamps the current correlation_id onto the request, then sends it.

        Stamping happens here rather than at ActionRequest construction because some
        requests are built once and re-sent many times (Rotation's failsafe responses,
        ActionWithValidation's retry loop); those must carry the id of the _decide()
        call that sent them, not of whenever they happened to be built.
        :param request: The ActionRequest to send to the Main Process.
        """
        request.correlation_id = self.correlation_id
        self.pipe.send(request)

    def emit(self, event_type: str, payload: Mapping[str, Any] | None = None) -> None:
        """
        Emit a Telemetry Record for the _decide() call currently in flight.

        Closes over the two things a Producer would otherwise repeat at every
        call site: the Correlation ID of the decision in flight, and the logger
        name its records are attributed to. Both are the base class's to know,
        so a subclass writes only what actually happened.

        Carries no Correlation ID when called outside a _decide() call - that is
        the truthful value, not a gap to paper over.
        :param event_type: What happened.
        :param payload: Event-specific detail.
        """
        emit_event(
            self.correlation_id, event_type, payload, logger_name=self._logger_name
        )

    # --- Pauses -------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def pause(
        self,
        *classes: type[DecisionMaker],
        reason: str,
        cancel_actions: bool = False,
    ) -> AsyncIterator[None]:
        """
        Hold a Pause on each of `classes`, in this Bot, for as long as the block
        runs::

            async with self.pause(MobsHitting, reason="no mobs for 60s"):
                ...

        A paused DecisionMaker has its loops cancelled and keeps its state; it
        runs again once every Pause on it is released. These are released when
        the block exits by any route: normally, on an exception, or because
        this DecisionMaker was itself paused and its decision cancelled.

        A class this Bot does not run is skipped. A Pause covers its exact class:
        pausing `MobsHitting` leaves a `MobsHitting` subclass running.
        :param reason: Why, for the `decision.paused` record and the logs.
        :param cancel_actions: Also cancel the Actions the paused DecisionMakers
            already sent to Main Process. Off by default: without it nothing is
            sent to Main Process, and an Action in flight runs to its end.
        :raises PauseNotDeclared: a class is not in this class's `pauses`.
        :raises ValueError: a class is this DecisionMaker's own, whose Pause
            would cancel the very block that holds it.
        """
        supervisor = self._supervision()
        self._check_declared(supervisor, classes)
        if type(self) in classes:
            raise ValueError(
                f"{self} cannot hold a Pause on its own class: it would cancel the "
                "block that holds it. Use pause_for_user to stop until a human "
                "resumes."
            )
        pauses = [
            Pause(supervisor.target(cls), repr(self), reason, PauseKind.SCOPED)
            for cls in dict.fromkeys(classes)
        ]
        held: list[Pause] = []
        try:
            for pause in pauses:
                if supervisor.hold(pause):
                    held.append(pause)
                    self.emit(DECISION_PAUSED, pause.payload())
            if cancel_actions and held:
                self.send(
                    ActionRequest(
                        f"{self} - Pause",
                        _cancel_only,
                        ign=self.data.ign,
                        priority=CANCEL_ACTIONS_PRIORITY,
                        cancels_itself=True,
                        requeue_if_not_scheduled=False,
                        cancel_tasks=[
                            action_name(pause.target.cls, self.data.ign)
                            for pause in held
                        ],
                    )
                )
            yield
        finally:
            for pause in held:
                if supervisor.release(pause):
                    self.emit(DECISION_RESUMED, pause.payload())

    def pause_for_user(self, *classes: type[DecisionMaker], reason: str) -> None:
        """
        Take a user-held Pause on each of `classes`, in this Bot: they stay
        paused until the user sends Discord `RESUME`, and nothing else releases
        them. For a DecisionMaker that needs a human; it may name its own class.
        :param reason: Why, for the `decision.paused` record and the logs.
        :raises PauseNotDeclared: a class is not in this class's `pauses`.
        """
        supervisor = self._supervision()
        self._check_declared(supervisor, classes)
        for cls in dict.fromkeys(classes):
            pause = Pause(supervisor.target(cls), USER, reason, PauseKind.USER)
            if supervisor.hold(pause):
                self.emit(DECISION_PAUSED, pause.payload())

    def _check_declared(
        self, supervisor: Supervisor, classes: Sequence[type[DecisionMaker]]
    ) -> None:
        declared = supervisor.declared(type(self))
        undeclared = [cls.__name__ for cls in classes if cls not in declared]
        if undeclared:
            raise PauseNotDeclared(
                f"{self} paused {', '.join(undeclared)}, which "
                f"{type(self).__name__}.pauses does not declare."
            )

    def _supervision(self) -> Supervisor:
        if self._supervisor is None:
            raise RuntimeError(
                f"{self} has no Supervisor: Pauses exist only once its Bot has started."
            )
        return self._supervisor

    # --- the legacy shim ------------------------------------------------------------

    def _disable_decision_makers(self, *args: str) -> None:
        """
        Legacy: pause the DecisionMakers of this Bot whose class is named, until
        `_enable_decision_makers` names them or the user sends Discord `RESUME`.

        Unlike `pause`, nothing scopes it: it outlives the decision that took it,
        and survives this DecisionMaker being paused. A DecisionMaker may name
        its own class. Disabling a disabled DecisionMaker does nothing more, and
        one `_enable_decision_makers` undoes it, whoever disabled it. Removed
        with the last mixin.
        :param args: The DecisionMakers' class names.
        """
        supervisor = self._supervision()
        for class_name in args:
            for cls in self._named(supervisor, class_name):
                gated: DecisionGatePayload = {"target": class_name}
                self.emit(DECISION_DISABLED, gated)
                if not any(p.kind is PauseKind.SHIM for p in supervisor.held(cls)):
                    supervisor.hold(
                        Pause(
                            supervisor.target(cls),
                            repr(self),
                            "_disable_decision_makers",
                            PauseKind.SHIM,
                        )
                    )

    def _enable_decision_makers(self, *args: str) -> None:
        """
        Legacy: end the `_disable_decision_makers` Pause on the DecisionMakers of
        this Bot whose class is named. Pauses of any other kind stay held.
        :param args: The DecisionMakers' class names.
        """
        supervisor = self._supervision()
        for class_name in args:
            for cls in self._named(supervisor, class_name):
                gated: DecisionGatePayload = {"target": class_name}
                self.emit(DECISION_ENABLED, gated)
                for pause in supervisor.held(cls):
                    if pause.kind is PauseKind.SHIM:
                        supervisor.release(pause)

    @staticmethod
    def _named(supervisor: Supervisor, class_name: str) -> list[type[DecisionMaker]]:
        """The classes this Bot runs that are called `class_name`."""
        return [
            cls
            for cls in dict.fromkeys(supervisor.classes())
            if cls.__name__ == class_name
        ]

    async def _validate_request_async(
        self,
        request: ActionRequest,
        predicate: Callable[..., Any],
        timeout: float,
        condition: threading.Condition | None = None,
        max_trials: int = 10,
    ) -> None:
        validator = ActionWithValidation(
            self.pipe,
            predicate,
            condition or self._condition,
            timeout,
            max_trials,
            correlation_id=self.correlation_id,
        )
        await validator.execute_async(request)

    async def _decision_loop(
        self, name: str, decide: Callable[[], Awaitable[None]]
    ) -> None:
        """
        Decide, throttle, repeat, until cancelled.

        The Supervisor runs one of these for each of `loops()`, so a
        DecisionMaker that owns more than one loop runs them all on the same
        machinery rather than reimplementing it - each loop mints its own
        Correlation IDs and reports under its own name.
        :param name: The task name this loop logs under.
        :param decide: One decision.
        """
        logger.info("%s has been enabled.", name)
        try:
            while True:
                self.correlation_id = str(uuid.uuid4())
                await decide()
                if self._throttle:
                    await asyncio.sleep(self._throttle)
        except asyncio.CancelledError:
            logger.info("%s has been disabled.", name)
            # TODO - see if cleanup is required
        except BaseException as e:
            logger.error("Exception occurred in %s: %s.", name, e)
            raise
