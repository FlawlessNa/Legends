import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from abc import ABC, abstractmethod

from .action_data import ActionRequest, ActionWithValidation
from .bot_data import BotData

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.INFO


class DecisionMaker(ABC):
    """
    Abstract base class to represent a decision maker of any kind.
    Each Bot consists of one or more DecisionMaker, which are cycled and called
    one at a time.
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

        # self.metadata["_disabled"].setdefault(
        #     f"{self.__class__.__name__}",
        # proxy = self.request_proxy(
        #         self.metadata,
        #         f"{self.__class__.__name__} - Disabler",
        #         "Event",
        #         True,
        #     )
        # # )
        # self.metadata["_disabled"][f'{self.__class__.__name__}'] = proxy
        breakpoint()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign})"

    @property
    def disabled(self) -> bool:
        return self.__class__.__name__ in self.metadata["_disabled"]

    @staticmethod
    def request_proxy(
        metadata: multiprocessing.managers.DictProxy,
        requester: str,
        primitive_type: str,
        multi_request: bool = False,
        *args,
        **kwargs,
    ):
        """
        Creates a Proxy for a primitive type.
        :param metadata: An EventProxy object that is set to notify the Manager of the
        request.
        :param requester: a string representing the requester.
        :param primitive_type: a string representing the primitive type.
        :param multi_request: If true, the proxy will not be popped from the metadata,
        so multiple requesters can use the same proxy.
        :return: a Proxy instance.
        """
        logger.log(LOG_LEVEL, f"Requesting {primitive_type} for {requester}.")
        notifier = metadata["proxy_request"]
        with notifier:  # Acquire the underlying Lock
            if requester in metadata and not isinstance(metadata[requester], tuple):
                logger.log(
                    LOG_LEVEL, f"Returning existing {primitive_type} for {requester}."
                )
                return metadata[requester]

            data = primitive_type, args, kwargs
            metadata[requester] = data
            while metadata[requester] == data:
                notifier.notify_all()
                notifier.wait(timeout=1)

        logger.log(LOG_LEVEL, f"Created {primitive_type} for {requester}.")
        if multi_request:
            # Clear the proxy after 120 seconds
            asyncio.get_running_loop().call_later(
                120, DecisionMaker._clear_proxy, metadata, requester
            )
            metadata["ignored_keys"] = metadata["ignored_keys"].union({requester})
            return metadata[requester]
        else:
            return metadata.pop(requester)

    @staticmethod
    def _clear_proxy(metadata: multiprocessing.managers.DictProxy, requester: str):
        with metadata["proxy_request"]:
            if requester in metadata:
                logger.log(LOG_LEVEL, f"Clearing {requester} from metadata.")
                metadata.pop(requester)
                metadata["ignored_keys"] = metadata["ignored_keys"] - {requester}

    @abstractmethod
    async def _decide(self, *args, **kwargs) -> None:
        pass

    async def _disable_decision_makers(self, *args: str) -> None:
        """
        Disables the given decision makers across all engines.
        :param args: The DecisionMakers (class names) to disable.
        :return:
        """
        for task in asyncio.all_tasks():
            if any(task.get_name().startswith(dm) for dm in args):
                print(f"{self} Cancelling task {task.get_name()}.")
                task.cancel()
                # await task
        # disabled = self.metadata["_disabled"]
        # for dm in args:
        #     disabled.add(dm)
        # self.metadata["_disabled"] = disabled

    def _enable_decision_makers(self, *args: str) -> None:
        """
        Enables the given decision makers across all engines.
        :param args: The DecisionMakers (class names) to enable.
        :return:
        """
        disabled = self.metadata["_disabled"]
        for dm in args:
            self.metadata["_disabled"].discard(dm)
        self.metadata["_disabled"] = disabled

    async def _validate_request_async(
        self,
        request: ActionRequest,
        predicate: callable,
        timeout: float,
        condition: multiprocessing.managers.ConditionProxy = None,  # noqa
        max_trials: int = 10
    ) -> None:
        validator = ActionWithValidation(
            self.pipe,
            predicate,
            condition or getattr(self, '_condition'),
            timeout,
            max_trials
        )
        await validator.execute_async(request)

    async def start(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        logger.log(LOG_LEVEL, f"{self} started.")
        tg.create_task(self._disabler_listener())
        try:
            while True:
                await self._decide(*args, **kwargs)
                if self._throttle:
                    await asyncio.sleep(self._throttle)
        except asyncio.CancelledError:
            breakpoint()
        except BaseException as e:
            breakpoint()
            logger.error(f"Exception occurred in {self}: {e}.")
            raise e

    async def _disabler_listener(self) -> None:
        """
        Listens for a disable request.
        :return:
        """
        while True:
            await asyncio.to_thread(...)
