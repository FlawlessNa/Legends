import math
import numpy as np
import time
from typing import Sequence

from botting.core import BotData
from botting.models_abstractions import BaseMob
from botting.utilities import Box


class   MobsHittingMixin:
    """
    Utility functions to determine mob count, mob positions, and closest mob direction.
    """
    data: BotData
    SMART_ROTATION_THRESHOLD = 4  # Used for "gravitate towards mobs" rotation mechanism
    TIME_ON_TARGET = 1.5  # Used for "smart rotation" mechanism

    @staticmethod
    def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob], **kwargs) -> int:
        """
        Given an image of arbitrary size, return the mob count of a specific mob found
        within that image.
        :param img: Image based on current character position and skill range.
        :param mobs: The mobs to look for.
        :return: Total number of mobs detected in the image
        """
        return sum([mob.get_mob_count(img, **kwargs) for mob in mobs])

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

    def _smart_rotation_target(self, mob_count_threshold: int) -> tuple[int, int]:
        """
        Determines the next target to move towards in a "smart way".
        Uses current on-screen location to get a wide view on the current platform.
        If there are mobs, target the "average" position of those in the direction
        where there are most. Otherwise, move towards the next feature in the cycle.
        :return:
        """
        if not hasattr(self, '_first_time_on_target'):
            self._first_time_on_target = True
        if not hasattr(self, '_last_target_reached_at'):
            self._last_target_reached_at = time.perf_counter()

        if (
            math.dist(
                self.data.current_minimap_position, self.data.next_target
            ) > self.SMART_ROTATION_THRESHOLD
        ):
            self._first_time_on_target = True
            return self.data.next_target

        # If we're on target, check if we've been on target for > time_limit seconds.
        if self._first_time_on_target:
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return self.data.next_target
        elif time.perf_counter() - self._last_target_reached_at < self.TIME_ON_TARGET:
            return self.data.next_target

        # Reach this code once you've been on target for > time_limit seconds.
        self._first_time_on_target = True
        # Check for mobs in the vicinity
        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            region = Box(
                left=max(0, x1 - 500),
                right=min(1024, x2 + 500),
                top=max(0, y1 - 100),
                bottom=min(768, y2 + 100),
            )
            cx = (x1 + x2) / 2
            cropped_img = region.extract_client_img(self.data.current_client_img)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if len(mobs_locations) >= mob_count_threshold:
                # Compute "center of mass" of mobs at the character's left and right
                center_x = [rect[0] + rect[2] / 2 for rect in mobs_locations]
                left_x = [rect_x for rect_x in center_x if rect_x < cx]
                right_x = [rect_x for rect_x in center_x if rect_x >= cx]

                minimap_width = self.data.current_minimap.map_area_width
                map_width = self.data.current_map.vr_width

                # Go towards left
                if len(left_x) > len(right_x):
                    avg_dist = sum([abs(rect_x - cx) for rect_x in left_x]) / len(
                        left_x
                    )
                    minimap_dist = min(int(avg_dist * minimap_width / map_width), 10)
                    minimap_x, minimap_y = self.data.current_minimap_position
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    minimum_x = curr_feature.left
                    if curr_feature.avoid_edges:
                        minimum_x += curr_feature.edge_threshold
                    target = (
                        max(minimap_x - minimap_dist, minimum_x),
                        curr_feature.top
                    )
                    return target

                # Go towards right
                else:
                    avg_dist = sum([abs(rect_x - cx) for rect_x in right_x]) / len(
                        right_x
                    )
                    minimap_dist = min(int(avg_dist * minimap_width / map_width), 10)
                    minimap_x, minimap_y = self.data.current_minimap_position
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    maximum_x = curr_feature.right
                    if curr_feature.avoid_edges:
                        maximum_x -= curr_feature.edge_threshold
                    target = (
                        min(minimap_x + minimap_dist, maximum_x),
                        curr_feature.top
                    )
                    return target

        self.data.update_attribute('next_feature')
        return self.data.next_feature.random()
