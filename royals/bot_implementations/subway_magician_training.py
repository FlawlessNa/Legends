import logging
import math
from functools import partial
from typing import Generator

from botting.core import Bot, BotMonitor, QueueAction
from .actions.pathfinding import get_to_target_pos
from .checks.mock import mock_check

logger = logging.getLogger(__name__)


class SubwayMagicianTraining(BotMonitor):
    def __init__(self, bot: Bot) -> None:
        super().__init__(bot)

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> list[callable]:
        return [self.get_to_next_point, self.attack_mobs]

    def get_to_next_point(self) -> Generator:
        while True:
            target = self.game_data.current_map.random_point()

            while math.dist(self.game_data.current_pos, target) > 5:  # TODO - Find proper threshold
                if self.watched_bot.rotation_lock.acquire(block=False):
                    task = get_to_target_pos(self.game_data.current_pos, target, self.game_data.current_map)
                    self.pipe_end.send(
                        QueueAction(
                            priority=10,
                            identifier="Map Rotation",
                            action=task,
                            is_cancellable=True,
                            is_map_rotation=True,
                            release_rotation_lock=True,
                            update_game_data=("current_pos",),
                        )
                    )
                yield

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
