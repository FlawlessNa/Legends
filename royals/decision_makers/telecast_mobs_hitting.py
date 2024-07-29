from botting.core.botv2.decision_maker import DecisionMaker
from botting.core.botv2.action_data import ActionRequest


class TelecastMobsHitting(DecisionMaker):

    def __init__(self, metadata, data, pipe):
        super().__init__(metadata, data, pipe)
        # self._on_screen_pos = None

    async def _decide(self) -> None:
        breakpoint()
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
