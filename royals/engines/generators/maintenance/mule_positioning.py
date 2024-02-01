import time
from botting.core import QueueAction
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MinimapData


class EnsureSafeSpot(IntervalBasedGenerator):
    """
    Basic Generator that ensures character has not moved.
    Useful for leeching mules in case they get hit.
    It only triggers a discord notification whenever the character has moved.
    """

    generator_type = "Maintenance"

    def __init__(
        self, data: MinimapData, interval: int = 2, deviation: int = 0
    ) -> None:
        super().__init__(data, interval, deviation)
        self._character_location = None

    def __repr__(self):
        return self.__class__.__name__

    @property
    def initial_data_requirements(self) -> tuple:
        return ("current_minimap_area_box",)

    def _update_continuous_data(self) -> None:
        self.data.update("current_minimap_position")
        if self._character_location is None:
            self._character_location = self.data.current_minimap_position

    def _failsafe(self) -> QueueAction | None:
        """
        No failsafe required
        :return:
        """
        pass

    def _exception_handler(self, e: Exception) -> None:
        raise e

    def _next(self) -> QueueAction | None:
        """
        Check if position has changed, and trigger discord notification if so.
        :return:
        """
        if (
            self._character_location != self.data.current_minimap_position
            and self.data.current_minimap_position is not None
        ):
            self._next_call = time.perf_counter() + 60
            return QueueAction(
                identifier="Mule has moved",
                priority=0,
                user_message=[f"{self.data.ign} has been moved"],
            )
