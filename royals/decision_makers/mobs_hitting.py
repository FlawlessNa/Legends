import asyncio
import logging
import math
import multiprocessing.connection
import multiprocessing.managers
import numpy as np
from functools import cached_property, partial
from typing import Sequence

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.models_abstractions import BaseMob
from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
    take_screenshot
)
from royals.actions import cast_skill
from royals.model.mechanics import RoyalsSkill

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')
LOG_LEVEL = logging.NOTSET


class _MobsHittingMixin:
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


class MobsHitting(DecisionMaker, _MobsHittingMixin):

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        mob_count_threshold: int,
        training_skill: str = None,
        **kwargs
    ) -> None:
        super().__init__(metadata, data, pipe)
        self.lock = self.request_proxy(self.metadata, f'{self}', "Lock")
        self.mob_threshold = mob_count_threshold
        self.training_skill = self._get_training_skill(training_skill)

        self.data.create_attribute(
            'current_client_img',
            lambda: take_screenshot(self.data.handle),
            threshold=0.1
        )
        self.data.create_attribute(
            "current_on_screen_position", self._get_on_screen_pos, threshold=1.0
        )

    def _hit_mobs(self, direction: str | None) -> ActionRequest:
        """
        Function to use to update the current on screen position of the character.
        :return:
        """
        _action = partial(
            cast_skill,
            self.data.handle,
            self.data.ign,
            self.training_skill,
            ready_at=0,
            direction=direction
        )

        return ActionRequest(
            _action,
            f'{self}',
            ign=self.data.ign,
            callback=self.lock.release
        )

    def _get_training_skill(self, training_skill_str: str) -> RoyalsSkill:
        if training_skill_str:
            return self.data.character.skills[training_skill_str]
        return self.data.character.skills[self.data.character.main_skill]

    @cached_property
    def _hide_minimap_box(self) -> Box:
        minimap_box = self.data.current_minimap.get_map_area_box(self.data.handle)
        return Box(
            max(
                0,
                minimap_box.left - CLIENT_HORIZONTAL_MARGIN_PX - 5,
            ),
            minimap_box.right + CLIENT_HORIZONTAL_MARGIN_PX + 5,
            max(
                0,
                minimap_box.top - CLIENT_VERTICAL_MARGIN_PX - 10,
            ),
            minimap_box.bottom + CLIENT_VERTICAL_MARGIN_PX + 5,
        )

    @cached_property
    def _hide_tv_smega_box(self) -> Box:
        return Box(left=700, right=1024, top=0, bottom=300)

    def _get_on_screen_pos(self) -> tuple[int, int]:
        """
        Function to use to update the current on screen position of the character.
        :return:
        """
        return self.data.character.get_onscreen_position(
            self.data.current_client_img,
            self.data.handle,
            [
                self._hide_minimap_box,
                self._hide_tv_smega_box,
            ],  # TODO - Add Chat Box as well into hiding
        )

    async def _decide(self) -> None:
        """
        Looks for the character on-screen, or use the last known location.
        Crop the image to the region of interest, centered around character location.
        Then, count the number of mobs in the region.
        If the number of mobs is greater than the threshold, cast the skill.
        :return:
        """
        logger.log(LOG_LEVEL, f"{self} is deciding.")
        await asyncio.to_thread(self.lock.acquire)

        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        closest_mob_direction = None

        if on_screen_pos:
            x, y = on_screen_pos
            if (
                self.training_skill.horizontal_screen_range
                and self.training_skill.vertical_screen_range
            ):
                region = Box(
                    left=x - self.training_skill.horizontal_screen_range,
                    right=x + self.training_skill.horizontal_screen_range,
                    top=y - self.training_skill.vertical_screen_range,
                    bottom=min(
                        y + self.training_skill.vertical_screen_range,
                        self.data.current_client_img.shape[0]-40
                    )
                )
                x, y = region.width / 2, region.height / 2
            else:
                region = self.data.current_map.detection_box
            cropped_img = region.extract_client_img(self.data.current_client_img)
            mobs = self.data.current_mobs
            nbr_mobs = 0
            for mob in mobs:
                nbr_mobs += mob.get_mob_count(cropped_img)

            if nbr_mobs >= self.mob_threshold:
                if self.training_skill.unidirectional:
                    mobs_locations = self.get_mobs_positions_in_img(
                        cropped_img, self.data.current_mobs
                    )
                    closest_mob_direction = self.get_closest_mob_direction(
                        (x, y), mobs_locations
                    )

                self.pipe.send(self._hit_mobs(closest_mob_direction))
                return
        await asyncio.to_thread(self.lock.release)
