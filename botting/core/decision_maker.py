import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from abc import ABC, abstractmethod

from .action_data import ActionRequest, ActionWithValidation
from .bot_data import BotData
from .proxy_factory import ProxyFactory

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.INFO


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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign})"

    @abstractmethod
    async def _decide(self, *args, **kwargs) -> None:
        pass

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
                logger.log(LOG_LEVEL, f"{self} is disabling {class_name}.")
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
                logger.log(LOG_LEVEL, f"{self} is re-enabling {class_name}.")
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
        logger.log(LOG_LEVEL, f"{name} has been enabled.")
        try:
            while True:
                await self._decide(*args, **kwargs)
                if self._throttle:
                    await asyncio.sleep(self._throttle)
        except asyncio.CancelledError:
            logger.log(LOG_LEVEL, f"{name} has been disabled.")
            pass  # TODO - see if cleanup is required
        except BaseException as e:
            logger.error(f"Exception occurred in {name}: {e}.")
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
