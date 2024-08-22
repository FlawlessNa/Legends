import cv2
import numpy as np
import logging
import os
import win32gui
from functools import cached_property, lru_cache

from botting import PARENT_LOG
from botting.core import BotData
from botting.utilities import Box
from royals.model.mechanics import RoyalsSkill

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.WARNING
DEBUG = True


class RebuffMixin:
    data: BotData
    _icons_directory = RoyalsSkill.icon_path
    _hsv_lower = np.array([0, 0, 0])
    _hsv_upper = np.array([179, 255, 53])
    MATCH_TEMPLATE_THRESHOLD = 0.60
    MATCH_ICON_THRESHOLD = 0.85
    # BOTTOM_ROWS: int = 8

    def _get_character_default_buffs(self, buff_type: str) -> list[RoyalsSkill]:
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
        return Box(left=right - 250, top=top + 45, right=right, bottom=85)

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

    def _buff_confirmation(self, buff: RoyalsSkill) -> bool:
        """
        Check if the rebuff was successful by looking for the buff icon.
        :return:
        """
        buff_icon = self._get_buff_icon(buff.name)
        haystack = self._icons_detection_region.extract_client_img(
            self.data.current_client_img
        )
        haystack = self._process_haystack(haystack)
        results = cv2.matchTemplate(haystack, buff_icon, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(results)
        self._debug(results, buff, haystack, buff_icon)
        # Start by finding actual location of the buff icon with reasonable threshold
        if max_val < self.MATCH_TEMPLATE_THRESHOLD:
            logger.log(
                LOG_LEVEL, f"Insufficient confidence {max_val:.4f} for {buff.name}."
            )
            return False
        else:
            # Then compare bottom of icon to check if darkened or not
            # (not darkened = buff is fresh)
            left, top = max_loc
            width, height = buff_icon.shape[::-1]
            target = haystack[top : top + height, left : left + width]
            return self._confirm_buff_freshness(target, buff_icon)

    def _confirm_buff_freshness(self, target: np.ndarray, icon) -> bool:
        """
        Given the on-screen icon to check, confirm if the buff is fresh or not.
        To do so, look at the bottom rows within the target image to see if a large
        proportion of it is black. If it is, then the buff is not fresh.
        :param target:
        :return:
        """
        # bottom_rows = target[-self.BOTTOM_ROWS:]
        return (target == icon).sum() / target.size > self.MATCH_ICON_THRESHOLD  # noqa

    def _debug(
        self, results: np.ndarray, buff: RoyalsSkill, haystack, buff_icon
    ) -> None:
        """
        Show the matchTemplate location for each actual buff, as well as the match
        results. Can also show processed images for each buff.
        :return:
        """
        if DEBUG:
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(results)
            left, top = max_loc
            width, height = self._get_buff_icon(buff.name).shape[::-1]
            target = haystack[top : top + height, left : left + width]
            score = (target == buff_icon).sum() / target.size
            print(f"{buff.name} has confidence {max_val} and score {score}.")
