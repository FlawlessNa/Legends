import time
import random

from functools import partial

from botting.core import QueueAction, controller
from botting.utilities import config_reader
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData


class PetFood(IntervalBasedGenerator):
    """
    Generator that triggers a pet food consumption every interval.
    Defaults: 15 minutes (900 seconds)
    """

    generator_type = "Maintenance"

    def __init__(
        self,
        data: MaintenanceData,
        interval: int = 900,
        keyname: str = "Pet Food",
        num_times: int = 1,
        deviation: float = 0.1,
    ) -> None:
        super().__init__(data, interval, deviation)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            keyname
        ]
        self._num_times = num_times

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._key})"

    @property
    def initial_data_requirements(self) -> tuple:
        """
        No initial data requirements.
        :return:
        """
        return tuple()

    def _update_continuous_data(self) -> tuple:
        """
        Nothing to updated for this generator.
        :return:
        """
        return tuple()

    def _next(self) -> QueueAction | None:
        self._next_call = (
            time.perf_counter() + random.uniform((1-self._deviation), (1+self._deviation)) * self.interval
        )
        action = partial(
            self._press_n_times,
            handle=self.data.handle,
            key=self._key,
            nbr_of_presses=self._num_times,
        )
        return QueueAction(self.__class__.__name__, 5, action)

    def _failsafe(self):
        """
        Nothing needed here.
        """
        pass

    def _exception_handler(self, e: Exception) -> None:
        """
        No errors expected. Re-raise if an error occurs.
        :param e:
        :return:
        """
        raise e

    @staticmethod
    async def _press_n_times(handle: int, key: str, nbr_of_presses: int = 1):
        for _ in range(nbr_of_presses):
            await controller.press(handle, key, silenced=True)


class MountFood(PetFood):
    def __init__(self,
                 data: MaintenanceData,
                 interval: int = 900,
                 keyname="Mount Food",
                 deviation: float = 0.1) -> None:
        super().__init__(data, interval, keyname, deviation=deviation)


class SpeedPill(PetFood):
    def __init__(self,
                 data: MaintenanceData,
                 interval: int = 600,
                 keyname="Speed Pill",
                 deviation: float = 0.01) -> None:
        super().__init__(data, interval, keyname, deviation=deviation)
