import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from abc import ABC, abstractmethod
from typing import Literal

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
    _type: Literal["Rotation", "AntiDetection", "Maintenance"]

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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign})"

    @staticmethod
    def request_proxy(
        metadata: multiprocessing.managers.DictProxy,
        requester: str,
        primitive_type: str,
        *args,
        **kwargs
    ):
        """
        Creates a Proxy for a primitive type.
        :param metadata: An EventProxy object that is set to notify the Manager of the
        request.
        :param requester: a string representing the requester.
        :param primitive_type: a string representing the primitive type.
        :return: a Proxy instance.
        """
        logger.log(LOG_LEVEL, f"Requesting {primitive_type} for {requester}.")
        notifier = metadata["proxy_request"]
        with notifier:  # Acquire the underlying Lock
            data = primitive_type, args, kwargs
            metadata[requester] = data
            notifier.notify()
            notifier.wait_for(lambda: metadata[requester] != data)
        logger.log(LOG_LEVEL, f"Created {primitive_type} for {requester}.")
        return metadata.pop(requester)

    @abstractmethod
    async def _decide(self) -> None:
        pass

    async def start(self) -> None:
        logger.log(LOG_LEVEL, f"{self} started.")
        try:
            while True:
                await self._decide()
                if self._throttle:
                    await asyncio.sleep(self._throttle)
        except Exception as e:
            logger.error(f"Exception occurred in {self}.")
            raise
