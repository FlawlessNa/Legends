import logging
import time

from abc import ABC, abstractmethod
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction
from botting.models_abstractions import Skill
from botting.utilities import Box, take_screenshot
from royals.actions import cast_skill
from royals.game_data import RotationData
from royals.actions import random_jump
from .hit_mobs import MobsHitting


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class Rotation(DecisionGenerator, MobsHitting, ABC):
    """
    Base class for all rotations, where a few helper methods are defined.
    """

    def __init__(
        self,
        data: RotationData,
        lock,
        training_skill: Skill,
        mob_threshold: int,
        teleport: Skill = None,
    ) -> None:
        super().__init__(data)
        self._lock = lock
        self.training_skill = training_skill
        self.mob_threshold = mob_threshold

        self._teleport = teleport
        self._deadlock_counter = 0
        self._prev_pos = None
        self._prev_rotation_actions = []

        self._on_screen_pos = None

    @property
    def data_requirements(self) -> tuple:
        return (
            "current_entire_minimap_box",
            "current_on_screen_position",
            "current_minimap_position",
            "last_cast",
            "last_position_change"
        )

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def _next(self):
        self._prev_pos = self.data.current_minimap_position
        self.data.update("current_minimap_position", "current_on_screen_position")

        self._set_next_target()
        hit_mobs = self._mobs_hitting()
        if hit_mobs:
            return QueueAction(
                identifier=f"Mobs Hitting - {self.training_skill.name}",
                priority=10,
                action=hit_mobs,
            )

        res = self._rotation()

        if res:
            action = QueueAction(
                identifier=self.__class__.__name__,
                priority=99,
                action=res,
                is_cancellable=getattr(self, "_is_cancellable", True),
                release_lock_on_callback=True,
            )
            self._prev_rotation_actions.append(action)
            if len(self._prev_rotation_actions) > 10:
                self._prev_rotation_actions.pop(0)
            return action

    @abstractmethod
    def _set_next_target(self) -> None:
        pass

    @abstractmethod
    def _rotation(self) -> partial | None:
        pass

    def _create_partial(self, action: callable) -> partial:
        args = (
            self.data.handle,
            self.data.ign,
            action.keywords["direction"],
        )
        kwargs = action.keywords.copy()
        kwargs.pop("direction", None)
        if action.func.__name__ == "teleport":
            kwargs.update(teleport_skill=self._teleport)
        return partial(action.func, *args, **kwargs)

    def _failsafe(self) -> QueueAction | None:
        reaction = QueueAction(
            identifier=f"FAILSAFE - {self.__class__.__name__}",
            priority=1,
            action=partial(random_jump, self.data.handle, self.data.ign),
            is_cancellable=False,
            release_lock_on_callback=True,
        )

        # If no change in position for 5 seconds, trigger failsafe
        now = time.perf_counter()
        if now - self.data.last_position_change > 10:
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to static position"
            )
            self.data.update("last_position_change")
            return reaction

        elif self._deadlock_counter > 30:
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to no path found"
            )
            self._deadlock_counter = 0
            return reaction

        elif (
            all(
                action == self._prev_rotation_actions[0]
                for action in self._prev_rotation_actions
            )
            and len(self._prev_rotation_actions) > 9
        ):
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to repeated actions"
            )
            self._deadlock_counter = 0
            self._prev_rotation_actions.clear()
            return reaction

    def _mobs_hitting(self) -> partial | None:
        res = None
        closest_mob_direction = None
        self._on_screen_pos = (
            self.data.current_on_screen_position
            if self.data.current_on_screen_position is not None
            else self._on_screen_pos
        )

        if self._on_screen_pos:
            x, y = self._on_screen_pos
            if (
                self.training_skill.horizontal_screen_range
                and self.training_skill.vertical_screen_range
            ):
                region = Box(
                    left=x - self.training_skill.horizontal_screen_range,
                    right=x + self.training_skill.horizontal_screen_range,
                    top=y - self.training_skill.vertical_screen_range,
                    bottom=y + self.training_skill.vertical_screen_range,
                )
                x, y = region.width / 2, region.height / 2
            else:
                region = self.data.current_map.detection_box

            cropped_img = take_screenshot(self.data.handle, region)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if self.training_skill.unidirectional and mobs_locations:
                closest_mob_direction = self.get_closest_mob_direction(
                    (x, y), mobs_locations
                )

            if len(mobs_locations) >= self.mob_threshold:
                self.data.update("last_mob_detection")
                res = partial(
                    cast_skill,
                    self.data.handle,
                    self.data.ign,
                    self.training_skill,
                    closest_mob_direction,
                )

        if (
            res
            and not self.data.character_in_a_ladder
            and time.perf_counter() - self.data.last_cast
            >= self.training_skill.animation_time + max(0.15, self.training_skill.animation_time * 0.05)
            # Small buffer to avoid more tasks being queued up - TODO - Improve this
        ):
            self.data.update("last_cast")
            return res
