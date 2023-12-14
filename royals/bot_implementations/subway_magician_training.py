import logging

from functools import partial
from typing import Generator

from botting import PARENT_LOG
from botting.core import Executor, DecisionEngine
from .checks.mock import mock_check

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')


class SubwayMagicianTraining(DecisionEngine):
    def __init__(self, bot: Executor) -> None:
        super().__init__(bot)
        self.game_data.update("current_minimap_area_box", "current_minimap_position", "current_entire_minimap_box")

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> list[callable]:
        return [self.get_to_next_point, self.attack_mobs]

    def attack_mobs(self) -> Generator:
        pass
        # while True:
        #     img = take_screenshot(self.watched_bot.handle)
        #     current_pos = self.watched_bot.character.get_character_position(img)
        #     mobs_pos = self.watched_bot.current_map.get_onscreen_mobs(img)
        #     if (
        #         min([current_pos - mob for mob in mobs_pos])
        #         < self.watched_bot.character.skills["Magic Claw"]
        #     ):
        #         self.pipe_end.send(
        #             QueueAction(
        #                 priority=1,
        #                 identifier="attack",
        #                 action=partial(_test_action, next(direction)),
        #             )
        #         )
        #     else:
        #         self.pipe_end.send(
        #             QueueAction(
        #                 priority=1,
        #                 identifier="move",
        #                 action=partial(_test_action, next(direction)),
        #             )
        #         )
        #
        #     yield
