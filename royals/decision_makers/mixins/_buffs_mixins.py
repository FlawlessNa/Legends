import cv2
import logging
import multiprocessing.connection
import numpy as np
import os
import random
import win32gui
from functools import cached_property, lru_cache

from botting import PARENT_LOG
from botting.core import ActionRequest, ActionWithValidation, BotData
from botting.utilities import Box
from royals.actions.skills_related_v2 import cast_skill_single_press
from royals.actions import priorities
from royals.model.characters import ALL_BUFFS
from royals.model.mechanics import RoyalsSkill, RoyalsBuff, RoyalsPartyBuff

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.WARNING
DEBUG = True


class RebuffMixin:
    data: BotData
    pipe: multiprocessing.connection.Connection
    _icons_directory = RoyalsSkill.icon_path
    _hsv_lower = np.array([0, 0, 0])
    _hsv_upper = np.array([179, 255, 53])

    def _get_character_default_buffs(
        self, buff_type: str
    ) -> list[RoyalsBuff | RoyalsPartyBuff]:
        return [
            skill
            for skill in self.data.character.skills.values()
            if skill.type == buff_type and skill.use_by_default
        ]

    @cached_property
    def _icons_detection_region(self) -> Box:
        """
        The region of the screen where the buff icons are located.
        """
        left, top, right, bottom = win32gui.GetClientRect(self.data.handle)
        return Box(left=right - 350, top=top + 45, right=right, bottom=85)

    @lru_cache
    def _get_buff_icon(self, buff_name: str) -> np.ndarray:
        """
        Get the buff icon from the detection images directory.
        """
        actual = cv2.imread(os.path.join(self._icons_directory, f"{buff_name}.png"))
        gray = cv2.cvtColor(actual, cv2.COLOR_BGR2GRAY)
        _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        return processed

    @staticmethod
    def _process_haystack(haystack_img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(haystack_img, cv2.COLOR_BGR2GRAY)
        _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        return processed

    def _buffs_confirmation(self, buffs: list[str]) -> bool:
        return all(self._buff_confirmation(buff) for buff in buffs)

    def _buff_confirmation(self, buff: str) -> bool:
        """
        Check if the rebuff was successful by looking for the buff icon.
        :return:
        """
        buff_icon = self._get_buff_icon(buff)
        haystack = self._icons_detection_region.extract_client_img(
            self.data.current_client_img
        )
        haystack = self._process_haystack(haystack)
        results = cv2.matchTemplate(haystack, buff_icon, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(results)
        self._debug(results, buff, haystack, buff_icon)
        # Start by finding actual location of the buff icon with reasonable threshold
        if max_val < ALL_BUFFS[buff].match_template_threshold:
            return False
        else:
            # Then compare bottom of icon to check if darkened or not
            # (not darkened = buff is fresh)
            left, top = max_loc
            width, height = buff_icon.shape[::-1]
            target = haystack[top : top + height, left : left + width]
            threshold = ALL_BUFFS[buff].match_icon_threshold
            return self._confirm_buff_freshness(target, buff_icon, threshold)

    @staticmethod
    def _confirm_buff_freshness(target: np.ndarray, icon, threshold) -> bool:
        """
        Given the on-screen icon to check, confirm if the buff is fresh or not.
        To do so, look at the bottom rows within the target image to see if a large
        proportion of it is black. If it is, then the buff is not fresh.
        :param target:
        :return:
        """
        return (target == icon).sum() / target.size > threshold  # noqa

    async def _cast_and_confirm(
        self,
        buffs: list[RoyalsSkill],
        condition: multiprocessing.managers.ConditionProxy,  # noqa
        predicate: callable = None,
    ) -> None:
        """
        Cast the buff and confirm that it was successful.
        :param buffs: The buff to cast.
        :param condition: The condition to wait on.
        :return:
        """
        if predicate is None:
            predicate = lambda: self._buffs_confirmation([buff.name for buff in buffs])
        request = ActionRequest(
            f"{self} - {[buff.name for buff in buffs]}",
            self._cast_skills_single_press,
            self.data.ign,
            priority=priorities.BUFFS,
            block_lower_priority=True,
            args=(self.data.handle, self.data.ign, buffs),
            log=True
        )
        validator = ActionWithValidation(
            self.pipe,
            predicate,
            condition,
            timeout=15.0,
            max_trials=20,
        )
        await validator.execute_async(request)

    @staticmethod
    def _randomized(duration: float) -> float:
        """
        Pick a random point within 80% and 85% of the buff's duration.
        :param duration: The duration of the buff.
        :return:
        """
        return duration * (0.8 + 0.05 * random.random())

    @staticmethod
    async def _cast_skills_single_press(
        handle: int, ign: str, skills: list[RoyalsSkill]
    ) -> None:
        for skill in skills:
            await cast_skill_single_press(handle, ign, skill)

    def _debug(self, results: np.ndarray, buff: str, haystack, buff_icon) -> None:
        """
        Show the matchTemplate location for each actual buff, as well as the match
        results.
        TODO - Can also show processed images for each buff.
        :return:
        """
        if DEBUG:
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(results)
            left, top = max_loc
            width, height = self._get_buff_icon(buff).shape[::-1]
            target = haystack[top : top + height, left : left + width]
            score = (target == buff_icon).sum() / target.size
            _skill = ALL_BUFFS[buff]
            print(
                f"{self}: {buff} has confidence {max_val:.2f} out of "
                f"{_skill.match_template_threshold} and score {score:.2f} out of "
                f"{_skill.match_icon_threshold}"
            )
