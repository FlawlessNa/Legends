import time
import random

from functools import partial

from botting.core import DecisionGenerator, QueueAction, controller
from botting.utilities import config_reader
from royals.game_data import MaintenanceData


class PetFood(DecisionGenerator):
    """
    Generator that triggers a pet food consumption every interval.
    Defaults: 10 minutes (600 seconds)
    """
    generator_type = "Maintenance"

    def __init__(
        self, data: MaintenanceData, interval: int = 600, keyname: str = "Pet Food"
    ) -> None:
        super().__init__(data)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            keyname
        ]
        self._interval = interval
        self._next_call = 0

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._key})"

    @property
    def data_requirements(self) -> tuple:
        return tuple()

    def _next(self) -> QueueAction | None:
        if time.perf_counter() >= self._next_call:
            self._next_call = (
                time.perf_counter() + random.uniform(0.9, 1.1) * self._interval
            )
            action = partial(
                controller.press,
                handle=self.data.handle,
                key=self._key,
                silenced=True,
                cooldown=0,
            )
            return QueueAction(self.__class__.__name__, 5, action)

    def _failsafe(self):
        """
        Nothing needed here.
        """
        pass


MountFood = partial(PetFood, keyname="Mount Food")  # Alias, same mechanism
SpeedPill = partial(PetFood, keyname="Speed Pill")