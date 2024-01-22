import cv2
import os
import random
import time
import win32gui

from functools import partial

from botting.core import QueueAction, GeneratorUpdate
from botting.models_abstractions import Skill
from botting.utilities import Box, find_image
from paths import ROOT

from royals.actions import cast_skill
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData


class Rebuff(IntervalBasedGenerator):
    """
    Generator for rebuffing. By default, a small random variation is removed from
    the skill duration.
    """
    generator_type = "Maintenance"

    def __init__(self,
                 data: MaintenanceData,
                 skill: Skill,
                 deviation: float = 0.1) -> None:
        super().__init__(data, skill.duration, deviation)
        self._skill = skill
        buff_path = os.path.join(ROOT,
                                 'royals/assets/detection_images/',
                                 f'{skill.name}.png')
        self._buff_icon = cv2.imread(buff_path)
        assert skill.duration > 0, f"Skill {skill.name} has no duration."

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._skill.name})"

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
        if self.data.available_to_cast:
            self.blocked = True
            self.data.update(available_to_cast=False)
            action = partial(cast_skill,
                             self.data.handle,
                             self.data.ign,
                             self._skill
                             )
            updater = GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={'blocked': False},
                game_data_kwargs={'available_to_cast': True}
            )
            return QueueAction(self._skill.name, 5, action, update_generators=updater)

    def _failsafe(self) -> None:
        """
        Look for a "fresh" buff icon at the top-right of the screen. If it is there,
        then the buff has successfully been cast and the interval can be reset.
        :return:
        """
        left, top, right, bottom = win32gui.GetClientRect(self.data.handle)
        buff_icon_box = Box(left=right-200, top=0, right=right, bottom=100)
        haystack = buff_icon_box.extract_client_img(self.data.current_client_img)
        check = find_image(haystack, self._buff_icon)
        if len(check) > 1:
            raise ValueError("Multiple buff icons found.")
        elif check:
            # Reset timer and return
            random_duration = self.interval * random.uniform(1 - self._deviation, 1)
            random_cooldown = self._skill.cooldown * random.uniform(1, 1 + self._deviation)
            self._next_call = time.perf_counter() + max(random_duration, random_cooldown)

    def _exception_handler(self, e: Exception) -> None:
        """
        No errors expected. Re-raise if an error occurs.
        :param e:
        :return:
        """
        raise e
