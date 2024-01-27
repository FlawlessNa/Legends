import cv2
import logging
import os
import random
import time
import win32gui

from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, GeneratorUpdate
from botting.models_abstractions import Skill
from botting.utilities import Box
from paths import ROOT

from royals.actions import cast_skill
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class Rebuff(IntervalBasedGenerator):
    """
    Generator for rebuffing. By default, a small random variation is removed from
    the skill duration.
    """

    generator_type = "Maintenance"

    def __init__(
        self,
        data: MaintenanceData,
        skill: Skill,
        deviation: float = 0.1,
        match_threshold: float = 0.997,
    ) -> None:
        super().__init__(data, skill.duration, deviation)
        self.match_threshold = match_threshold
        self._skill = skill
        buff_path = os.path.join(
            ROOT, "royals/assets/detection_images/", f"{skill.name}.png"
        )
        self._buff_icon = cv2.imread(buff_path)
        assert skill.duration > 0, f"Skill {skill.name} has no duration."
        self._skip_once = True

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
        if self._skip_once:  # To avoid double-casting when unnecessary
            self._skip_once = False
            return

        self.blocked = True
        self.data.update(available_to_cast=False)
        action = partial(cast_skill, self.data.handle, self.data.ign, self._skill)
        updater = GeneratorUpdate(
            generator_id=id(self),
            generator_kwargs={"blocked": False},
            game_data_kwargs={"available_to_cast": True},
        )
        return QueueAction(self._skill.name, 5, action, update_generators=updater)

    def _failsafe(self) -> None:
        """
        Look for a "fresh" buff icon at the top-right of the screen. If it is there,
        then the buff has successfully been cast and the interval can be reset.
        :return:
        """
        left, top, right, bottom = win32gui.GetClientRect(self.data.handle)
        buff_icon_box = Box(left=right - 150, top=top + 45, right=right, bottom=85)
        haystack = buff_icon_box.extract_client_img(self.data.current_client_img)
        results = cv2.matchTemplate(haystack, self._buff_icon, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, _, _ = cv2.minMaxLoc(results)
        if max_val > self.match_threshold:
            logger.info(f"{self._skill.name} has been cast with confidence {max_val}.")
            # Reset timer and return
            random_duration = self.interval * random.uniform(
                1 - self._deviation, 1 - self._deviation / 2
            )
            random_cooldown = self._skill.cooldown * random.uniform(
                1, 1 + self._deviation
            )
            self._next_call = time.perf_counter() + max(
                random_duration, random_cooldown
            )
            self._skip_once = True

    def _exception_handler(self, e: Exception) -> None:
        """
        No errors expected. Re-raise if an error occurs.
        :param e:
        :return:
        """
        raise e
