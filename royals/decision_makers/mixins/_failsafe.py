import logging
import multiprocessing.connection
import time

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
    _tb_sentinels: list[dict]
    _bool_sentinels: list[dict]
    _sentinel_starts_at: float

    def _create_time_based_sentinel(
        self,
        attribute: str,
        method: callable,
        threshold: float,
        response: ActionRequest,
    ) -> None:
        sentinel = {
            "attribute": attribute,
            "method": method,
            "threshold": threshold,
            "response": response,
            "triggered": False,
        }
        self._tb_sentinels.append(sentinel)

    def _create_bool_sentinel(
        self,
        attribute: str,
        method: callable,
        trigger_when_true: bool,
        response: ActionRequest,
    ) -> None:
        sentinel = {
            "attribute": attribute,
            "method": method,
            "trigger_when_true": trigger_when_true,
            "response": response,
            "triggered": False,
        }
        self._bool_sentinels.append(sentinel)

    def _failsafe_checks(self) -> None:
        if time.perf_counter() < self._sentinel_starts_at:
            return
        self._check_time_based_sentinels()
        self._check_bool_sentinels()

    def _check_time_based_sentinels(self) -> None:
        for sentinel in self._tb_sentinels:
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

    def _check_bool_sentinels(self) -> None:
        for sentinel in self._bool_sentinels:
            attribute = sentinel["attribute"]
            method = sentinel["method"]
            if sentinel["trigger_when_true"] and method(attribute):
                if not sentinel["triggered"]:
                    sentinel["triggered"] = True
                    logger.warning(
                        f"{self.data.ign} - {attribute} Failsafe triggered."
                    )
                    self.pipe.send(sentinel["response"])
            elif not sentinel["trigger_when_true"] and not method(attribute):
                if not sentinel["triggered"]:
                    sentinel["triggered"] = True
                    logger.warning(
                        f"{self.data.ign} - {attribute} Failsafe triggered."
                    )
                    self.pipe.send(sentinel["response"])
            else:
                sentinel["triggered"] = False
