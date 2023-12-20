import logging
import multiprocessing

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionEngine, Executor
from royals import royals_ign_finder, RoyalsData
from royals.models_implementations.minimaps import LudiFreeMarketTemplate as Ludi

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class LudiFreeMarketRoaming(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(self, log_queue: multiprocessing.Queue, bot: Executor) -> None:
        super().__init__(log_queue, bot)
        self._game_data = RoyalsData(self.handle, self.ign)
        self.game_data.current_minimap = Ludi()
        self.game_data.update("current_minimap_area_box", "current_minimap_position")

    @property
    def game_data(self) -> RoyalsData:
        return self._game_data

    def items_to_monitor(self) -> list[callable]:
        return []

    def next_map_rotation(self) -> list[callable]:
        return [self.random_rotation]

    def random_rotation(self) -> None:
        generator = random_rotation(self.game_data)
        while True:
            action = next(generator)
            if action:
                if self.watched_bot.rotation_lock.acquire(block=False):
                    logger.debug(
                        "Rotation Lock acquired. Next action is being sent to main queue."
                    )
                    self.pipe_end.send(
                        QueueAction(
                            priority=10,
                            identifier="Map Rotation",
                            action=action,
                            is_cancellable=True,
                            is_map_rotation=True,
                            update_game_data=("current_minimap_position",),
                        )
                    )
            yield
