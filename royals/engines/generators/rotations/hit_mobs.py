import cv2
import math
import numpy as np
import time

from functools import partial
from typing import Sequence

from botting.core import QueueAction, DecisionGenerator
from botting.models_abstractions import BaseMob, Skill
from botting.utilities import take_screenshot, Box
from royals import RoyalsData
from royals.actions import cast_skill


class MobsHitting(DecisionGenerator):
    def _failsafe(self):
        pass

    def __init__(self, data: RoyalsData, skill: Skill, mob_threshold: int = 2) -> None:
        self.data = data
        self.skill = skill
        self.mob_threshold = mob_threshold

    def __call__(self):
        self._on_screen_pos = None
        self._last_cast = time.perf_counter()
        return iter(self)

    def __next__(self) -> QueueAction | None:
        res = None
        closest_mob_direction = None
        self.data.update("current_on_screen_position")
        self._on_screen_pos = (
            self.data.current_on_screen_position
            if self.data.current_on_screen_position is not None
            else self._on_screen_pos
        )

        if self._on_screen_pos:
            x, y = self._on_screen_pos
            if self.skill.horizontal_screen_range and self.skill.vertical_screen_range:
                region = Box(
                    left=x - self.skill.horizontal_screen_range,
                    right=x + self.skill.horizontal_screen_range,
                    top=y - self.skill.vertical_screen_range,
                    bottom=y + self.skill.vertical_screen_range,
                )
                x, y = region.width / 2, region.height / 2
            else:
                region = self.data.current_map.detection_box

            cropped_img = take_screenshot(self.data.handle, region)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if self.skill.unidirectional:
                closest_mob_direction = self.get_closest_mob_direction(
                    (x, y), mobs_locations
                )

            if len(mobs_locations) >= self.mob_threshold:
                self.data.update(last_mob_detection=time.perf_counter())
                res = partial(
                    cast_skill,
                    self.data.handle,
                    self.data.ign,
                    self.skill,
                    closest_mob_direction,
                )

        if (
            res
            and not self.data.character_in_a_ladder
            and time.perf_counter() - self._last_cast
            >= self.skill.animation_time
            * 1.05  # Small buffer to avoid more tasks being queued up - TODO - Improve this
        ):
            self._last_cast = time.perf_counter()
            return QueueAction(
                identifier=f"{self.__class__.__name__} - {self.skill.name}",
                priority=10,
                action=res,
            )

    @staticmethod
    def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob]) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found within that image.
        :param img: Potentially cropped image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img) for mob in mobs])

    @staticmethod
    def get_mobs_positions_in_img(
        img: np.ndarray, mobs: list[BaseMob]
    ) -> list[Sequence[int]]:
        """
        Given an image of arbitrary size, return the positions of a specific mob found within that image.
        :param img: Potentially cropped image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: List of mob positions found in the image.
        """
        return [pos for mob in mobs for pos in mob.get_onscreen_mobs(img)]

    @staticmethod
    def get_closest_mob_direction(
        character_pos: Sequence[float], mobs: list[Sequence[int]]
    ) -> str | None:
        """
        Given current character position and list of detected mobs on screen,
        return the (horizontal) direction of the closest mob relative to character.
        :param character_pos: Rectangle (x, y, w, h)
        :param mobs: List of rectangles (x, y, w, h)
        :return: Direction of closest mob relative to character.
        """
        if not mobs:
            return None
        centers = [(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2) for rect in mobs]
        distances = [math.dist(character_pos, center) for center in centers]

        # Find minimum distance in terms of absolute value, but retain its sign
        closest_mob_idx = np.argmin(np.abs(distances))
        return "left" if distances[closest_mob_idx] < 0 else "right"
