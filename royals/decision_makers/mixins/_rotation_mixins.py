import itertools
import logging
import math

from botting import PARENT_LOG
from botting.core import BotData
from royals.model.mechanics import (
    MinimapPathingMechanics,
    Movements,
    RoyalsSkill,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class NextTargetMixin:
    """
    Utility function to set next target.
    """

    data: BotData
    DISTANCE_THRESHOLD = 10

    def _create_rotation_attributes(self) -> None:
        if self.data.current_minimap.feature_cycle:
            cycle = itertools.cycle(self.data.current_minimap.feature_cycle)
            self.data.create_attribute(
                "next_feature",
                lambda: next(cycle),
            )
            self.data.create_attribute(
                "next_target",
                self._update_next_target_from_cycle,
                initial_value=self.data.next_feature.random(),
            )
        else:
            self.data.create_attribute(
                "next_target",
                self.data.current_minimap.random_point,
            )
            self.data.create_attribute(
                "next_feature",
                lambda: self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                ),
            )

    def _update_next_target_from_cycle(self) -> None:
        """
        Updates the next target from the feature cycle.
        :return:
        """
        if (
            math.dist(self.data.current_minimap_position, self.data.next_target)
            > self.DISTANCE_THRESHOLD
        ):
            return self.data.next_target
        else:
            self.data.update_attribute("next_feature")
            return self.data.next_feature.random()

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
            > self.DISTANCE_THRESHOLD
        ):
            return self.data.next_target
        else:
            next_target = self.data.current_minimap.random_point()
            self.data.next_feature = self.data.current_minimap.get_feature_containing(
                next_target
            )
            return next_target


class MovementsMixin:
    data: BotData
    NO_PATH_FOUND_THRESHOLD: float = 15.0

    def _create_pathing_attributes(
        self,
        duration: float,
    ) -> None:
        movement_handler = Movements(
            self.data.ign,
            self.data.handle,
            self.data.character.skills.get("Teleport"),
            self.data.current_minimap,
        )

        self.data.create_attribute(
            "path",
            lambda: movement_handler.compute_path(
                self.data.current_minimap_position, self.data.next_target
            ),
            threshold=0.1,
        )
        self.data.create_attribute(
            "movements",
            lambda: movement_handler.path_into_movements(self.data.path),
            threshold=0.1,
        )
        self.data.create_attribute(
            "action",
            lambda: movement_handler.movements_into_action(
                self.data.movements, duration
            ),
        )
