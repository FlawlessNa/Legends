import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from functools import cached_property

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)
from royals.actions.skills_related_v2 import cast_skill
from royals.model.interface import LargeClientChatFeed
from royals.model.mechanics import RoyalsSkill
from .mixins import MobsHittingMixin, MinimapAttributesMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


class MobsHitting(MobsHittingMixin, MinimapAttributesMixin, DecisionMaker):
    ON_SCREEN_THRESHOLD = 0.5

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        mob_count_threshold: int,
        training_skill: str = None,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self.lock = self.request_proxy(self.metadata, f"{self}", "Lock")
        self.mob_threshold = mob_count_threshold
        self.training_skill = self._get_skill_from_str(training_skill)
        self._create_minimap_attributes()
        self.data.create_attribute(
            "current_on_screen_position",
            self._get_on_screen_pos,
            threshold=1.0,
            # error_handler=...,  # TODO - Implement error handler
        )

    def _hit_mobs(self, direction: str | None) -> ActionRequest:
        """
        Function to use to update the current on screen position of the character.
        :return:
        """
        inputs = cast_skill(self.data.handle, self.data.ign, self.training_skill)

        return ActionRequest(
            f"{self}",
            self._cap_duration,
            ign=self.data.ign,
            priority=2,
            cancel_tasks=[f"Rotation({self.data.ign})"],
            block_lower_priority=True,
            callbacks=[self.lock.release],
            cancels_itself=True,
            log=True,
            args=(inputs,),
        )

    @staticmethod
    async def _cap_duration(  # TODO - If this works, cleanup.
        inputs: controller.KeyboardInputWrapper,
    ) -> None:
        """
        Function to use to update the current on screen position of the character.
        :return:
        """
        try:
            await asyncio.wait_for(inputs.send(), timeout=inputs.duration * 2)
        except asyncio.TimeoutError:
            breakpoint()

    def _get_skill_from_str(self, skill_str: str) -> RoyalsSkill:
        if skill_str:
            return self.data.character.skills[skill_str]
        return self.data.character.skills[self.data.character.main_skill]

    @cached_property
    def _hide_minimap_box(self) -> Box:
        minimap_box = self.data.current_entire_minimap_box
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
        return Box(left=800, right=1024, top=0, bottom=200)

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
            ],  # TODO - Add Chat Box  + fixed UI as well into hiding
            acceptance_threshold=self.ON_SCREEN_THRESHOLD,
        )

    async def _decide(self) -> None:
        """
        Looks for the character on-screen, or use the last known location.
        Crop the image to the region of interest, centered around character location.
        Then, count the number of mobs in the region.
        If the number of mobs is greater than the threshold, cast the skill.
        :return:
        """
        await asyncio.to_thread(self.lock.acquire)

        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        closest_mob_direction = None

        if on_screen_pos:
            x1, y1, x2, y2 = on_screen_pos
            if (
                self.training_skill.horizontal_screen_range
                and (
                    self.training_skill.vertical_screen_range
                    or (
                        self.training_skill.vertical_up_screen_range
                        and self.training_skill.vertical_down_screen_range
                    )
                )
            ):
                horizontal = self.training_skill.horizontal_screen_range
                vertical_up = (
                    self.training_skill.vertical_up_screen_range
                    or self.training_skill.vertical_screen_range
                )
                vertical_down = (
                    self.training_skill.vertical_down_screen_range
                    or self.training_skill.vertical_screen_range
                )
                region = Box(  # TODO - finetune the region better? (Right now it uses smallest region)
                    left=x1 - horizontal // 2,
                    right=x2 + horizontal // 2,
                    top=y2 - vertical_up // 2,
                    bottom=min(
                        y2 + vertical_down // 2,
                        LargeClientChatFeed._chat_typing_area.top,  # noqa
                    ),
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
                    breakpoint()  # TODO
                    mobs_locations = self.get_mobs_positions_in_img(
                        cropped_img, self.data.current_mobs
                    )
                    closest_mob_direction = self.get_closest_mob_direction(
                        (x, y), mobs_locations
                    )
                logger.log(LOG_LEVEL, f"{self} is about to hit {nbr_mobs} mobs.")
                self.pipe.send(self._hit_mobs(closest_mob_direction))
                return
        await asyncio.to_thread(self.lock.release)
