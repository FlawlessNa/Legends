import math
import numpy as np
from typing import Sequence

from botting.core import BotData
from botting.models_abstractions import BaseMob


class MobsHittingMixin:
    """
    Utility functions to determine mob count, mob positions, and closest mob direction.
    """
    data: BotData

    def mob_count_in_img(self, img: np.ndarray, mobs: list[BaseMob], **kwargs) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found
        within that image.
        :param img: Image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img, self.data.handle, **kwargs) for mob in mobs])

    def get_mobs_positions_in_img(
        self, img: np.ndarray, mobs: list[BaseMob], **kwargs
    ) -> list[Sequence[int]]:
        """
        Given an image of arbitrary size, return the positions of a specific mob
        found within that image.
        :param img: Potentially cropped image based on current character position and
        skill range.
        :param mobs: The mobs to look for.
        :return: List of mob positions found in the image.
        """
        return [
            pos for mob in mobs
            for pos in mob.get_onscreen_mobs(img, self.data.handle, **kwargs)
        ]

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
        horizontal_distance = centers[closest_mob_idx][0] - character_pos[0]
        return "left" if horizontal_distance < 0 else "right"
