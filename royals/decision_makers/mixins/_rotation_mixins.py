import itertools
import logging
import math

from botting import PARENT_LOG
from botting.core import BotData
from royals.model.mechanics import (
    Movements,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class NextTargetMixin:
    """
    Utility function to set next target.
    """

    data: BotData
    BASE_ROTATION_THRESHOLD = 10  # Used for basic rotation mechanism
    SMART_ROTATION_THRESHOLD = 2  # Used for "gravitate towards mobs" rotation mechanism

    def _create_rotation_attributes(self, cycle=None) -> None:
        if self.data.current_minimap.feature_cycle:

            if cycle is None:
                self.data.create_attribute(
                    "feature_cycle",
                    lambda: itertools.cycle(self.data.current_minimap.feature_cycle),
                )
            self.data.create_attribute(
                "next_feature",
                lambda: next(self.data.feature_cycle),
            )
            self.data.create_attribute(
                "next_target",
                self._update_next_target_from_cycle,
                initial_value=self.data.next_feature.random(),
            )
        else:
            self.data.create_attribute(
                "next_target",
                self._update_next_random_target,
                initial_value=self.data.current_minimap.random_point(),
            )
            self.data.create_attribute(
                "next_feature",
                lambda: self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                ),
            )
        self.data.create_attribute("has_rotation_attributes", lambda: True)

    def _update_next_target_from_cycle(self) -> None:
        """
        Updates the next target from the feature cycle.
        :return:
        """
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target)
            > self.BASE_ROTATION_THRESHOLD
        ):
            return self.data.next_target
        else:
            self.data.update_attribute("next_feature")
            return self.data.next_feature.random()

    def _update_next_target_random(self) -> None:
        """
        Updates the next target randomly.
        :return:
        """
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target)
            > self.BASE_ROTATION_THRESHOLD
        ):
            return self.data.next_target
        else:
            return self.data.current_minimap.random_point()

    def _converge_towards_mobs(self):
        """
        Sets the next target to a central point among the detected mobs in a given
        direction. # TODO -> Mimics the SmartRotationGenerator
        :return:
        """
        pass

    def _update_next_random_target(self):
        """
        Sets the next target from the feature cycle.
        :return:
        """
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target)
            > self.BASE_ROTATION_THRESHOLD
        ):
            return self.data.next_target
        else:
            next_target = self.data.current_minimap.random_point()
            self.data.next_feature = self.data.current_minimap.get_feature_containing(
                next_target
            )
            return next_target

    def _set_fixed_target(self, target: tuple[int, int]) -> None:
        """
        Move to the location where the buffs are cast.
        """
        if self.data.has_rotation_attributes:
            # Overwrite how the next_target attribute is set until the rebuff is done
            self.data.create_attribute(
                "next_target",
                lambda: target,
            )
            self._reset_flag = True


class MovementsMixin:
    data: BotData
    NO_PATH_FOUND_THRESHOLD: float = 15.0

    def _create_pathing_attributes(
        self,
        duration: float,
    ) -> None:
        self.data.create_attribute("action_duration", lambda: duration)
        self.data.create_attribute(
            "movement_handler",
            lambda: Movements(
                self.data.ign,
                self.data.handle,
                self.data.character.skills.get("Teleport"),
                self.data.current_minimap
            )
        )

        self.data.create_attribute(
            "path",
            lambda: self.data.movement_handler.compute_path(
                self.data.current_minimap_position, self.data.next_target
            ),
            threshold=0.1,
        )
        self.data.create_attribute(
            "movements",
            lambda: self.data.movement_handler.path_into_movements(self.data.path),
            threshold=0.1,
        )
        self.data.create_attribute(
            "action",
            lambda: self.data.movement_handler.movements_into_action(
                self.data.movements,
                duration,
                getattr(self.data, 'speed_multiplier', 1.0)
            ),
        )
        self.data.create_attribute("has_pathing_attributes", lambda: True)

    def _always_release_keys_on_actions(self):
        actions = self.data.movement_handler.movements_into_action(
            self.data.movements, self.data.action_duration
        )
        if actions is not None:
            for key in actions.keys_held:
                if key not in actions.forced_key_releases:
                    actions.forced_key_releases.append(key)
        return actions
