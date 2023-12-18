import logging
import multiprocessing

from typing import Generator

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionEngine, Executor
from royals import royals_ign_finder, RoyalsData
from royals.models_implementations.characters import Magician
from royals.models_implementations.minimaps import KerningLine1Area1
from royals.models_implementations.maps import SubwayLine1Area1

from .actions import random_rotation
from .actions import hit_mobs

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class SubwayMagicianTraining(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(self, log_queue: multiprocessing.Queue, bot: Executor) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.current_map = SubwayLine1Area1()
        self.game_data.current_minimap = self.game_data.current_map.minimap
        self.game_data.character = Magician(self.ign, "large")
        self.game_data.update(
            "current_minimap_area_box",
            "current_minimap_position",
            "current_entire_minimap_box",
        )

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        return (
            []
        )  # TODO - Add a check that looks whether current node is walkable. if not walkable and static + 10s, then add some movement

    def next_map_rotation(self) -> list[callable]:
        return [self.random_rotation, self.train]

    def train(self) -> Generator:
        func_id = 0
        generator = hit_mobs.hit_closest_in_range(
            self.game_data, self.game_data.character.skills["Magic Claw"]
        )
        while True:
            action = next(generator)
            if action:
                if self.watched_bot.rotation_locks[func_id].acquire(block=False):
                    logger.debug(
                        f"Rotation Lock {func_id} acquired. Next action is being sent to main queue."
                    )
                    self.pipe_end.send(
                        QueueAction(
                            priority=3,
                            identifier="Hit Mobs",
                            action=action,
                            is_cancellable=False,
                            lock_id=func_id,
                            update_game_data={
                                "current_direction": action.keywords.get("direction")
                            },
                        )
                    )
            yield

    def random_rotation(self) -> Generator:
        func_id = 1
        generator = random_rotation(self.game_data)
        while True:
            action = next(generator)
            if action:
                if self.watched_bot.rotation_locks[func_id].acquire(block=False):
                    logger.debug(
                        f"Rotation Lock {func_id} acquired. Next action is being sent to main queue."
                    )
                    self.pipe_end.send(
                        QueueAction(
                            priority=10,
                            identifier="Map Rotation",
                            action=action,
                            is_cancellable=True,
                            is_map_rotation=True,
                            lock_id=func_id,
                            update_game_data=("current_minimap_position",),
                        )
                    )
            yield
