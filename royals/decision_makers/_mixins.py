import itertools
import math
import numpy as np
from typing import Sequence

from botting.core import BotData
from botting.models_abstractions import BaseMob


class _NextTargetMixin:
    """
    Utility function to set next target.
    """
    data: BotData
    DISTANCE_THRESHOLD = 10

    def _create_rotation_attributes(self) -> None:
        if self.data.current_minimap.feature_cycle:
            cycle = itertools.cycle(self.data.current_minimap.feature_cycle)
            self.data.create_attribute(
                'next_feature',
                lambda: next(cycle),
            )
            self.data.create_attribute(
                'next_target',
                self._update_next_target_from_cycle,
                initial_value=self.data.next_feature.random(),
            )
        else:
            self.data.create_attribute(
                'next_target',
                self.data.current_minimap.random_point,
            )
            self.data.create_attribute(
                'next_feature',
                lambda: self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                )
            )

    def _update_next_target_from_cycle(self) -> None:
        """
        Updates the next target from the feature cycle.
        :return:
        """
        if math.dist(
            self.data.current_minimap_position, self.data.next_target
        ) > self.DISTANCE_THRESHOLD:
            return self.data.next_target
        else:
            self.data.update_attribute('next_feature')
            return self.data.next_feature.random()

    def _converge_towards_mobs(self):
        """
        Sets the next target to a central point among the detected mobs in a given
        direction. # TODO -> Mimics the SmartRotationGenerator
        :return:
        """
        pass

    def _update_next_random_target(self):
        """
        Sets the next target from the feature cycle.
        :return:
        """
        if math.dist(
            self.data.current_minimap_position, self.data.next_target
        ) > self.DISTANCE_THRESHOLD:
            return self.data.next_target
        else:
            next_target = self.data.current_minimap.random_point()
            self.data.next_feature = self.data.current_minimap.get_feature_containing(
                next_target
            )
            return next_target


class _MobsHittingMixin:
    """
    Utility functions to determine mob count, mob positions, and closest mob direction.
    """
    @staticmethod
    def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob]) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found
        within that image.
        :param img: Image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img) for mob in mobs])

    @staticmethod
    def get_mobs_positions_in_img(
        img: np.ndarray, mobs: list[BaseMob]
    ) -> list[Sequence[int]]:
        """
        Given an image of arbitrary size, return the positions of a specific mob
        found within that image.
        :param img: Potentially cropped image based on current character position and
        skill range.
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
        horizontal_distance = centers[closest_mob_idx][0] - character_pos[0]
        return "left" if horizontal_distance < 0 else "right"


class _MinimapAttributesMixin:
    data: BotData
    MINIMAP_POS_REFRESH_RATE = 0.1

    def _get_minimap_pos(self) -> tuple[int, int]:
        return self.data.current_minimap.get_character_positions(
            self.data.handle, map_area_box=self.data.current_minimap_area_box
        ).pop()

    def _create_minimap_attributes(self) -> None:
        self.data.create_attribute(
            'current_minimap_area_box',
            lambda: self.data.current_minimap.get_map_area_box(self.data.handle)
        )
        self.data.create_attribute(
            'current_minimap_position',
            self._get_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE
        )
        self.data.create_attribute(
            'current_entire_minimap_box',
            lambda: self.data.current_minimap.get_entire_minimap_box(self.data.handle)
        )
