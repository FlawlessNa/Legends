import logging
import multiprocessing.connection

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class TimeBasedFailsafeMixin:
    """
    Use this DecisionMaker to implement time-based fail safes for the bot.
    Each failsafe should monitor a specific condition, usually related to a BotData
    attribute.
    The failsafe may then trigger a specific action to correct the condition.
    """
    data: BotData
    pipe: multiprocessing.connection.Connection
    _sentinels: list[dict]

    def _create_time_based_sentinel(
        self,
        attribute: str,
        method: callable,
        threshold: float,
        response: ActionRequest
    ) -> None:
        sentinel = {
            "attribute": attribute,
            "method": method,
            "threshold": threshold,
            "response": response,
            "triggered": False
        }
        self._sentinels.append(sentinel)

    def _failsafe_checks(self) -> None:
        for sentinel in self._sentinels:
            attribute = sentinel["attribute"]
            method = sentinel["method"]
            threshold = sentinel["threshold"]
            if method(attribute) > threshold:
                if not sentinel["triggered"]:
                    sentinel["triggered"] = True
                    logger.warning(
                        f"{self.data.ign} - {attribute} has been static for > "
                        f"{threshold:.2f}s."
                    )
                    self.pipe.send(sentinel["response"])
            else:
                sentinel["triggered"] = False
