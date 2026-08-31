import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import uuid
from abc import ABC, abstractmethod

from botting.logging_config import PARENT_LOG
from botting.telemetry import emit_event
from botting.telemetry_events import (
    DECISION_DISABLED,
    DECISION_ENABLED,
    DecisionGatePayload,
)

from .action_data import ActionRequest, ActionWithValidation
from .bot_data import BotData
from .proxy_factory import ProxyFactory

logger = logging.getLogger(__name__)


class DecisionMaker(ABC):
    """
    Abstract base class to represent a decision maker of any kind.
    Each Bot consists of one or more DecisionMaker, which are wrapped as asyncio.Tasks
    and executed concurrently.
    When called, a DecisionMaker may return an ActionRequest container,
    which will be sent to the Main Process to be executed there.
    """

    _throttle: float = None

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs,
    ) -> None:
        self.metadata = metadata
        self.data = data
        self.pipe = pipe
        self._proxies = ProxyFactory(metadata)

        class_name = self.__class__.__name__
        self._disabler = self._proxies.shared(class_name, "disabler", "Condition")
        self._enabler = self._proxies.shared(class_name, "enabler", "Condition")
        self.decision_task = None
        self._enabled = True

        # Identifies the current _decide() call. Minted by task(), read by send() and
        # by any Producer that must carry the id into a procedure itself. Set by the
        # base class only - subclasses never assign it. None until the first _decide().
        self.correlation_id: str | None = None

        # Logger name this DecisionMaker's Telemetry Records are attributed to,
        # following whichever convention its own module follows: botting.*
        # modules name their logger after __name__, maple.* modules prefix
        # __name__ with PARENT_LOG. Getting this right is what keeps a record
        # attributable to the subsystem that produced it.
        module = type(self).__module__
        self._logger_name = (
            module
            if module == PARENT_LOG or module.startswith(f"{PARENT_LOG}.")
            else f"{PARENT_LOG}.{module}"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign})"

    @abstractmethod
    async def _decide(self, *args, **kwargs) -> None:
        pass

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

    def emit(self, event_type: str, payload: dict | None = None) -> None:
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

    def _disable_decision_makers(self, *args: str, self_only: bool = False) -> None:
        """
        Disables the given decision makers across all engines.
        :param args: The DecisionMakers (class names) to disable.
        :return:
        """
        for class_name in args:
            key = f"proxy/shared/{class_name}/disabler"
            condition_proxy = self.metadata.get(key, None)
            if condition_proxy is not None:
                gated: DecisionGatePayload = {"target": class_name}
                self.emit(DECISION_DISABLED, gated)
                with condition_proxy:
                    condition_proxy.notify_all()  # noqa

    def _enable_decision_makers(self, *args: str, self_only: bool = False) -> None:
        """
        Enables the given decision makers across all engines.
        :param args: The DecisionMakers (class names) to enable.
        :return:
        """
        for class_name in args:
            key = f"proxy/shared/{class_name}/enabler"
            condition_proxy = self.metadata.get(key, None)
            if condition_proxy is not None:
                gated: DecisionGatePayload = {"target": class_name}
                self.emit(DECISION_ENABLED, gated)
                with condition_proxy:
                    condition_proxy.notify_all()  # noqa

    async def _validate_request_async(
        self,
        request: ActionRequest,
        predicate: callable,
        timeout: float,
        condition: multiprocessing.managers.ConditionProxy = None,  # noqa
        max_trials: int = 10,
    ) -> None:
        validator = ActionWithValidation(
            self.pipe,
            predicate,
            condition or getattr(self, "_condition"),
            timeout,
            max_trials,
            correlation_id=self.correlation_id,
        )
        await validator.execute_async(request)

    async def start(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        tg.create_task(
            asyncio.to_thread(self._disabler_task, tg, *args, **kwargs),
            name=f"{self} - Disabler",
        )
        tg.create_task(
            asyncio.to_thread(self._enabler_task, tg, *args, **kwargs),
            name=f"{self} - Enabler",
        )
        self.decision_task = tg.create_task(
            self.task(*args, **kwargs), name=f"{self}"
        )

    async def task(self, *args, **kwargs) -> None:
        """
        The main task of the DecisionMaker.
        :return:
        """
        name = asyncio.current_task().get_name()
        logger.info("%s has been enabled.", name)
        try:
            while True:
                self.correlation_id = str(uuid.uuid4())
                await self._decide(*args, **kwargs)
                if self._throttle:
                    await asyncio.sleep(self._throttle)
        except asyncio.CancelledError:
            logger.info("%s has been disabled.", name)
            pass  # TODO - see if cleanup is required
        except BaseException as e:
            logger.error("Exception occurred in %s: %s.", name, e)
            # breakpoint()
            raise e

    def _enabler_task(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        while True:
            with self._enabler:
                self._enabler.wait()
                if not self._enabled:
                    self.decision_task = tg.create_task(
                        self.task(*args, **kwargs), name=f"{self}"
                    )
                    self._enabled = True

    def _disabler_task(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        """
        Listens for a disable request.
        :return:
        """
        while True:
            with self._disabler:
                # When notified, cancel the task
                self._disabler.wait()
                if self._enabled:
                    self.decision_task.cancel()
                    self._enabled = False
