import math
import random
import time
from functools import partial

from botting.core import QueueAction, GeneratorUpdate
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.actions import random_jump
from royals.game_data import MinimapData
from royals.models_implementations.mechanics.path_into_movements import get_to_target


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
            self._character_location = self.data.current_minimap_position
            return QueueAction(
                identifier="Mule has moved",
                priority=0,
                user_message=[f"{self.data.ign} has been moved"],
            )


class ResetIdleSafeguard(IntervalBasedGenerator):
    """
    Basic Generator that moves character at every interval.
    Used to ensure that actions such as rebuffing still go through after some time.
    """

    generator_type = "Maintenance"

    def __init__(
        self, data: MinimapData, interval: int = 300, deviation: int = 0.1
    ) -> None:
        super().__init__(data, interval, deviation)
        self.data.update(allow_teleport=False)
        self._next_call = time.perf_counter() + interval  # don't trigger immediately
        self._stage = self._jumps_done = self._deadlock_counter = 0
        self._target = self._feature = None

    def __repr__(self):
        return f"{self.__class__.__name__}({self.data.ign})"

    @property
    def initial_data_requirements(self) -> tuple:
        return (
            "current_entire_minimap_box",
            "current_minimap_area_box",
            "current_minimap_position",
            "minimap_grid",
        )

    def _update_continuous_data(self) -> None:
        self.data.update("current_minimap_position")
        if self._target is None or self._feature is None:
            self._target = self.data.current_minimap_position
            self._feature = self.data.current_minimap.get_feature_containing(
                self._target
            )

        if self._stage == 0:
            self._num_jumps = random.randint(1, 3)
            self._stage += 1

    def _failsafe(self) -> QueueAction | None:
        """
        No failsafe required
        :return:
        """
        if self._deadlock_counter >= 30:
            raise Exception(f"{self} has been deadlocked for too long")

    def _exception_handler(self, e: Exception) -> None:
        raise e

    def _next(self) -> QueueAction | None:
        """
        Triggers 1-3 random jumps and return to initial location.
        :return:
        """
        if self._stage == 1:
            if self._jumps_done < self._num_jumps:
                self._jumps_done += 1
                self.blocked = True
                return QueueAction(
                    identifier=f"{self} Random Jump {self._jumps_done}",
                    priority=1,
                    action=partial(random_jump, self.data.handle, self.data.ign),
                    update_generators=GeneratorUpdate(
                        generator_id=id(self),
                        generator_kwargs={"blocked": False},
                    ),
                )

            else:
                self._jumps_done = 0
                self._stage += 1

        elif self._stage == 2:
            if (
                math.dist(self.data.current_minimap_position, self._target) > 2
                or self.data.current_minimap.get_feature_containing(self._target)
                != self._feature
            ):
                actions = get_to_target(
                    self.data.current_minimap_position,
                    self._target,
                    self.data.current_minimap,
                )
                if actions:
                    self._deadlock_counter = 0
                    args = (
                        self.data.handle,
                        self.data.ign,
                        actions[0].keywords["direction"],
                    )
                    kwargs = actions[0].keywords.copy()
                    kwargs.pop("direction", None)
                    action = partial(actions[0].func, *args, **kwargs)
                    self.blocked = True
                    return QueueAction(
                        identifier=f"{self} Returning to Initial Location",
                        priority=1,
                        action=action,
                        update_generators=GeneratorUpdate(
                            generator_id=id(self),
                            generator_kwargs={"blocked": False},
                        ),
                    )
                else:
                    self._deadlock_counter += 1

            else:
                self._stage = 0
                self._next_call = time.perf_counter() + self.interval
