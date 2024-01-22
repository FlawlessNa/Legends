import logging
import random
import time

from abc import ABC, abstractmethod
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction, GeneratorUpdate, controller
from botting.models_abstractions import Skill
from botting.utilities import Box, config_reader
from royals.actions import cast_skill
from royals.game_data import RotationData
from royals.actions import random_jump
from royals.engines.generators.rotations.hit_mobs import MobsHitting
from royals.models_implementations.mechanics.path_into_movements import get_to_target


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class RotationGenerator(DecisionGenerator, MobsHitting, ABC):
    """
    Base class for all rotations, where a few helper methods are defined.
    """
    generator_type = "Rotation"

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

        self.next_target = (0, 0)
        self._teleport = teleport

        self._deadlock_counter = 0  # For Failsafe
        self._last_pos_change = time.perf_counter()  # For Failsafe
        self._prev_pos = None  # For Failsafe
        self._prev_rotation_actions = []  # For Failsafe

        self._on_screen_pos = None  # For Mobs Hitting

        self._minimap_key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Minimap Toggle"
        ]

    @property
    def initial_data_requirements(self) -> tuple:
        return (
            "current_entire_minimap_box",
            "current_map_area_box",
            "current_minimap_position",
            "minimap_grid",
        )

    def _update_continuous_data(self) -> None:
        self._prev_pos = self.data.current_minimap_position
        self.data.update("current_minimap_position", "current_on_screen_position")
        self._on_screen_pos = (
            self.data.current_on_screen_position
            if self.data.current_on_screen_position is not None
            else self._on_screen_pos
        )
        self.actions = get_to_target(
            self.data.current_minimap_position,
            self.next_target,
            self.data.current_minimap,
        )

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def _next(self):
        self._set_next_target()
        hit_mobs = self._mobs_hitting()
        if hit_mobs:
            self.data.update(available_to_cast=False)
            updater = GeneratorUpdate(
                game_data_kwargs={"available_to_cast": True}
            )
            return QueueAction(
                identifier=f"Mobs Hitting - {self.training_skill.name}",
                priority=10,
                action=hit_mobs,
                update_generators=updater,
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
        now = time.perf_counter()
        if self._prev_pos != self.data.current_minimap_position:
            self._last_pos_change = now

        if not self.actions:
            self._deadlock_counter += 1
        else:
            self._deadlock_counter = 0

        reaction = QueueAction(
            identifier=f"FAILSAFE - {self.__class__.__name__}",
            priority=1,
            action=partial(random_jump, self.data.handle, self.data.ign),
            is_cancellable=False,
            release_lock_on_callback=True,
        )

        # If no change in position for 10 seconds, trigger failsafe
        if now - self._last_pos_change > 10:
            logger.warning(
                f"{self.__class__.__name__} Failsafe Triggered Due to static position"
            )
            self._last_pos_change = now
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
            self._prev_rotation_actions.clear()
            return reaction

    def _mobs_hitting(self) -> partial | None:
        res = None
        closest_mob_direction = None

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
            cropped_img = region.extract_client_img(self.data.current_client_img)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if self.training_skill.unidirectional and mobs_locations:
                closest_mob_direction = self.get_closest_mob_direction(
                    (x, y), mobs_locations
                )

            if len(mobs_locations) >= self.mob_threshold:
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
            and self.data.available_to_cast
        ):
            return res

    def _exception_handler(self, e: Exception) -> QueueAction | None:
        logger.info(f"{self.__class__.__name__} Exception: {e}")
        self.blocked = True

        if self._error_counter >= 4:
            logger.critical("Minimap Fix Failed, Minimap Position cannot be determined")
            raise e

        if not self.data.current_minimap.get_minimap_state(self.data.handle) == "Full":
            return QueueAction(
                identifier=f"Toggling Minimap - {self.__class__.__name__}",
                priority=1,
                action=partial(controller.press,
                               self.data.handle,
                               self._minimap_key,
                               cooldown=1),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={'blocked': False},
                )
            )
        else:
            self.data.update("current_entire_minimap_box", "current_minimap_area_box")
            return QueueAction(
                identifier=f"Move Cursor away from Minimap - {self.__class__.__name__}",
                priority=1,
                action=partial(controller.mouse_move,
                               self.data.handle,
                               target=(random.randint(300, 600),
                                       random.randint(300, 600)
                                       ),
                               cooldown=1),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={'blocked': False},
                )
            )
