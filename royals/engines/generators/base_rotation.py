import logging
import random
import time

from abc import ABC, abstractmethod
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction, GeneratorUpdate, controller
from botting.utilities import Box, config_reader
from royals.actions import cast_skill
from royals.game_data import RotationData
from royals.actions import random_jump
from royals.engines.generators.rotations.hit_mobs import MobsHitting
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.models_implementations.mechanics import RoyalsSkill


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class RotationGenerator(DecisionGenerator, MobsHitting, ABC):
    """
    Base class for all rotations, where a few helper methods are defined.
    """

    generator_type = "Rotation"

    def __init__(
        self,
        data: RotationData,
        training_skill: RoyalsSkill,
        mob_threshold: int,
        teleport: RoyalsSkill = None,
    ) -> None:
        super().__init__(data)
        self.training_skill = training_skill
        self.mob_threshold = mob_threshold
        self.actions = []

        self.next_target = (0, 0)
        self._teleport = teleport

        self._deadlock_counter = self._deadlock_type_2 = 0  # For Failsafe
        self._last_pos_change = time.perf_counter()  # For Failsafe
        self._prev_pos = self._prev_action = None  # For Failsafe
        self._prev_rotation_actions = []  # For Failsafe

        self._on_screen_pos = None  # For Mobs Hitting

        self._minimap_key = eval(
            config_reader("keybindings", self.data.ign, "Non Skill Keys")
        )["Minimap Toggle"]
        self.data.update(allow_teleport=True if teleport is not None else False)

    @property
    def initial_data_requirements(self) -> tuple:
        return (
            "current_entire_minimap_box",
            "current_minimap_area_box",
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
        if self.actions:
            self._prev_action = self.actions[0]

        self.actions = get_to_target(
            self.data.current_minimap_position,
            self.next_target,
            self.data.current_minimap,
            self.data.handle,
            controller.key_binds(self.data.ign)["jump"],
            self._teleport,
            self.data.ign,
        )

    def __repr__(self):
        return f"{self.__class__.__name__}"

    def _next(self):
        if getattr(self.data, "next_target", None) is not None:
            self.next_target = self.data.next_target
        else:
            self._set_next_target()
        hit_mobs = self._mobs_hitting()
        if hit_mobs:
            return hit_mobs

        return self._rotation()

    @abstractmethod
    def _set_next_target(self) -> None:
        pass

    def _rotation(self) -> QueueAction | None:
        if self.actions:
            res = self.actions[0]
            if self._prev_action is not None and self._deadlock_type_2 < 50:
                # If the same action is repeated and position is changing, all good
                # If position remains, fire an action.
                if (
                    res.func == self._prev_action.func
                    and res.args == self._prev_action.args
                    and self._prev_pos != self.data.current_minimap_position
                ):
                    self._prev_action = None
                    self._deadlock_type_2 += 1
                    return

            self._deadlock_type_2 = 0
            action = QueueAction(
                identifier=self.__class__.__name__,
                priority=99,
                action=res,
                # is_cancellable=cancellable,
                # release_lock_on_callback=True,
            )

            self._prev_rotation_actions.append(res)
            if len(self._prev_rotation_actions) > 5:
                self._prev_rotation_actions.pop(0)
            return action

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
            priority=97,
            action=partial(
                random_jump,
                self.data.handle,
                controller.key_binds(self.data.ign)["jump"],
            ),
            is_cancellable=False,
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
            self.data.update("current_entire_minimap_box", "current_minimap_area_box")
            return reaction

        # elif (
        #     all(
        #         action.func == self._prev_rotation_actions[0].func
        #         and action.args == self._prev_rotation_actions[0].args
        #         and action.keywords == self._prev_rotation_actions[0].keywords
        #         for action in self._prev_rotation_actions
        #     )
        #     and len(self._prev_rotation_actions) > 4
        # ):
        #     logger.warning(
        #         f"{self.__class__.__name__} Failsafe Triggered Due to repeated actions"
        #     )
        #     self._prev_rotation_actions.clear()
        #     return reaction

    def _mobs_hitting(self) -> QueueAction | None:
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
            mobs = self.data.current_mobs
            nbr_mobs = 0
            for mob in mobs:
                nbr_mobs += mob.get_mob_count(cropped_img)

            if nbr_mobs >= self.mob_threshold:
                if self.training_skill.unidirectional:
                    mobs_locations = self.get_mobs_positions_in_img(
                        cropped_img, self.data.current_mobs
                    )
                    closest_mob_direction = self.get_closest_mob_direction(
                        (x, y), mobs_locations
                    )

                res = partial(
                    cast_skill,
                    self.data.handle,
                    self.data.ign,
                    self.training_skill,
                    self.data.casting_until,
                    closest_mob_direction,
                )
        # if res and not self.data.character_in_a_ladder and self.data.available_to_cast:
        if res and time.perf_counter() - self.data.casting_until > 0:
            self.data.update(
                casting_until=time.perf_counter() + self.training_skill.animation_time,
                available_to_cast=False,
            )
            updater = GeneratorUpdate(game_data_kwargs={"available_to_cast": True})
            return QueueAction(
                identifier=f"Mobs Hitting - {self.training_skill.name}",
                priority=98,
                action=res,
                update_generators=updater,
            )

    def _exception_handler(self, e: Exception) -> QueueAction | None:
        logger.warning(f"{self.__class__.__name__} Exception: {e}")
        self.blocked = True

        if self._error_counter >= 4:
            logger.critical("Minimap Fix Failed, Minimap Position cannot be determined")
            raise e

        if not self.data.current_minimap.get_minimap_state(self.data.handle) == "Full":
            return QueueAction(
                identifier=f"Toggling Minimap - {self.__class__.__name__}",
                priority=1,
                action=partial(
                    controller.press, self.data.handle, self._minimap_key, True
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={"blocked": False},
                    game_data_args=(
                        "current_entire_minimap_box",
                        "current_minimap_area_box",
                    ),
                ),
            )
        else:
            self.data.update("current_entire_minimap_box", "current_minimap_area_box")
            return QueueAction(
                identifier=f"Move Cursor away from Minimap - {self.__class__.__name__}",
                priority=1,
                action=partial(
                    controller.mouse_move,
                    self.data.handle,
                    target=(random.randint(300, 600), random.randint(300, 600)),
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={"blocked": False},
                ),
            )
