import logging
from functools import partial
from typing import Generator

from royals.core import Bot, BotMonitor, QueueAction
from royals.utilities import take_screenshot
from .checks.mock import mock_check
from .checks.mobs_in_range import get_closest_mob_direction

logger = logging.getLogger(__name__)


class SubwayMagicianTraining(BotMonitor):
    def __init__(self, bot: Bot) -> None:
        super().__init__(bot)

    def items_to_monitor(self) -> list[callable]:
        return [partial(mock_check, self.pipe_end)]

    def next_map_rotation(self) -> Generator:
        while True:
            img = take_screenshot(self.watched_bot.handle)
            current_pos = self.watched_bot.character.get_character_position(img)
            mobs_pos = self.watched_bot.current_map.get_onscreen_mobs(img)
            if (
                min([current_pos - mob for mob in mobs_pos])
                < self.watched_bot.character.skills["Magic Claw"]
            ):
                self.pipe_end.send(
                    QueueAction(
                        priority=1,
                        identifier="attack",
                        action=partial(_test_action, next(direction)),
                    )
                )
            else:
                self.pipe_end.send(
                    QueueAction(
                        priority=1,
                        identifier="move",
                        action=partial(_test_action, next(direction)),
                    )
                )

            yield
