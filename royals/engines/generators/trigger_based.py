import logging
import time

from abc import ABC, abstractmethod
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction
from royals.game_data import MaintenanceData


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class TriggerBasedGenerator(DecisionGenerator, ABC):
    """
    Base class for generators that perform a check at regular intervals and may trigger
    actions based on that check.
    """

    def __init__(
        self,
        data: MaintenanceData,
        interval: int,
    ) -> None:
        super().__init__(data)
        self.interval = interval
        self._next_call = time.perf_counter()
        self._fail_count = 0

    def _get_status(self) -> str:
        if time.perf_counter() < self._next_call:
            return "Idle"
        else:
            return getattr(self.data, f"{repr(self)}_status")

    def _set_status(self, status: str):
        setattr(self.data, f"{repr(self)}_status", status)

    def _failsafe(self):
        if self._fail_count > 10:
            logger.critical(f"{repr(self)} has failed too many times. Stopping.")
            return QueueAction(
                identifier=f"{repr(self)} Failsafe",
                priority=1,
                action=partial(lambda: RuntimeError, f"{repr(self)} Failsafe"),
                user_message=[f"{repr(self)} has failed too many times. Stopping."]
            )

    def _next(self):
        status = self._get_status()
        if status == "Idle":
            return
        elif status == "Setup":
            return self._setup()
        elif status == "Ready":
            self._update_attributes()
            self._set_status("Idle")
            return self._trigger()  # Trigger responsible for setting status to "Done"
        elif status == "Done":
            if not self._confirm_cleaned_up():
                return QueueAction(
                    identifier=f"{self.__class__.__name__} - Cleanup",
                    priority=1,
                    action=self._cleanup_action(),
                    is_cancellable=False,
                    update_game_data={f"{repr(self)}_status": "Done"},
                )
            else:
                self._set_status("Ready")
                self._next_call = time.perf_counter() + self.interval
                self._fail_count = 0
                return

    @abstractmethod
    def _cleanup_action(self) -> partial:
        pass

    @abstractmethod
    def _confirm_cleaned_up(self) -> bool:
        pass

    @abstractmethod
    def _update_attributes(self) -> None:
        pass

    @abstractmethod
    def _setup(self) -> QueueAction:
        pass

    @abstractmethod
    def _trigger(self) -> QueueAction:
        pass
