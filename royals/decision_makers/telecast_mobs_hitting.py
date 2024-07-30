import asyncio
import multiprocessing.connection
import multiprocessing.managers
from functools import cached_property

from botting.core.botv2.bot_data import BotData
from botting.core.botv2.decision_maker import DecisionMaker
from botting.core.botv2.action_data import ActionRequest
from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)

from royals.model.mechanics import RoyalsSkill


class TelecastMobsHitting(DecisionMaker):
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
        self.mob_threshold = mob_count_threshold
        self.training_skill = self._get_training_skill(training_skill)

        self.data.create_attribute(
            "current_on_screen_position", self._get_on_screen_pos, threshold=1.0
        )
        breakpoint()

    def _get_training_skill(self, training_skill_str: str) -> RoyalsSkill:
        if training_skill_str:
            return self.data.character.skills[training_skill_str]
        return self.data.character.skills[self.data.character.main_skill]

    @cached_property
    def _hide_minimap_box(self) -> Box:
        minimap_box = self.data.current_minimap_area_box
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
        return self.data.character.get_onscreen_position(
            None,
            self.data.handle,
            [
                self._hide_minimap_box,
                self._hide_tv_smega_box,
            ],  # TODO - Add Chat Box as well into hiding
        )

    async def _decide(self) -> None:
        # ons_screen_pos = self.data.on_screen_pos
        # breakpoint()
        await asyncio.sleep(10)
        raise Exception
        # self._on_screen_pos = self.data.on_screen_pos or self._on_screen_pos
        # res = None
        # closest_mob_direction = None
        #
        # if self._on_screen_pos:
        #     x, y = self._on_screen_pos
        #     if (
        #         self.training_skill.horizontal_screen_range
        #         and self.training_skill.vertical_screen_range
        #     ):
        #         region = Box(
        #             left=x - self.training_skill.horizontal_screen_range,
        #             right=x + self.training_skill.horizontal_screen_range,
        #             top=y - self.training_skill.vertical_screen_range,
        #             bottom=y + self.training_skill.vertical_screen_range,
        #         )
        #         x, y = region.width / 2, region.height / 2
        #     else:
        #         region = self.data.current_map.detection_box
        #     cropped_img = region.extract_client_img(self.data.current_client_img)
        #     mobs = self.data.current_mobs
        #     nbr_mobs = 0
        #     for mob in mobs:
        #         nbr_mobs += mob.get_mob_count(cropped_img)
        #
        #     if nbr_mobs >= self.mob_threshold:
        #         if self.training_skill.unidirectional:
        #             mobs_locations = self.get_mobs_positions_in_img(
        #                 cropped_img, self.data.current_mobs
        #             )
        #             closest_mob_direction = self.get_closest_mob_direction(
        #                 (x, y), mobs_locations
        #             )
        #
        #         res = partial(
        #             cast_skill,
        #             self.data.handle,
        #             self.data.ign,
        #             self.training_skill,
        #             self.data.casting_until,
        #             closest_mob_direction,
        #         )
        # if res and time.perf_counter() - self.data.casting_until > 0:
        #     self.data.update(
        #         casting_until=time.perf_counter() + self.training_skill.animation_time,
        #         available_to_cast=False,
        #     )
        #     updater = GeneratorUpdate(game_data_kwargs={"available_to_cast": True})
        #     return QueueAction(
        #         identifier=f"Mobs Hitting - {self.training_skill.name}",
        #         priority=99,
        #         action=res,
        #         update_generators=updater,
        #         is_cancellable=True
        #     )
