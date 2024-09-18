import itertools
import logging
import math
import time

from botting import PARENT_LOG
from botting.core import BotData
from botting.utilities import Box
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
    SMART_ROTATION_THRESHOLD = 4  # Used for "gravitate towards mobs" rotation mechanism
    TIME_ON_TARGET = 1.5  # Used for "smart rotation" mechanism
    MIN_MOBS_THRESHOLD = 2

    def _create_rotation_attributes(
        self,
        *,
        cycle=None,
        smart_rotation: bool = False,
        mob_count_threshold: int = None,
    ) -> None:

        if smart_rotation is True:
            self.data.create_attribute('has_smart_rotation', lambda: True)
            assert mob_count_threshold is not None, (
                "Mob count threshold must be provided for smart rotation."
            )
            self.data.create_attribute('mob_threshold', lambda: mob_count_threshold)

        # If the map has a cycle provided for features, use it
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
            if not self.data.has_smart_rotation:
                self.data.create_attribute(
                    "next_target",
                    self._update_next_target_from_cycle,
                    initial_value=self.data.next_feature.random(),
                )
            else:
                self.data.create_attribute(
                    "next_target",
                    self._smart_rotation_target,
                    initial_value=self.data.next_feature.random(),
                )
        # If not cycle provided for current map, rotate at random
        else:
            if not self.data.has_smart_rotation:
                self.data.create_attribute(
                    "next_target",
                    self._update_next_random_target,
                    initial_value=self.data.current_minimap.random_point(),
                )
            else:
                self.data.create_attribute(
                    "next_target",
                    self._smart_rotation_target,
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

    def _smart_rotation_target(self) -> tuple[int, int]:
        """
        Determines the next target to move towards in a "smart way".
        Uses current on-screen location to get a wide view on the current platform.
        If there are mobs, target the "average" position of those in the direction
        where there are most. Otherwise, move towards the next feature in the cycle.
        :return:
        """
        assert hasattr(self.data, 'mob_threshold'), "_mob_threshold attribute must be set."
        assert hasattr(self, 'get_mobs_positions_in_img'), (
            f"MobsHittingMixin must be inherited by {self} for smart rotation"
        )
        if not hasattr(self, '_first_time_on_target'):
            self._first_time_on_target = True
        if not hasattr(self, '_last_target_reached_at'):
            self._last_target_reached_at = time.perf_counter()

        if (
            math.dist(
                self.data.current_minimap_position, self.data.next_target
            ) > self.SMART_ROTATION_THRESHOLD
        ):
            self._first_time_on_target = True
            return self.data.next_target

        # If we're on target, check if we've been on target for > time_limit seconds.
        if self._first_time_on_target:
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return self.data.next_target
        elif time.perf_counter() - self._last_target_reached_at < self.TIME_ON_TARGET:
            return self.data.next_target

        # Reach this code once you've been on target for > time_limit seconds.
        self._first_time_on_target = True
        # Check for mobs in the vicinity
        self.data.update_attribute('current_client_img')
        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            region = Box(
                left=max(0, x1 - 500),
                right=min(1024, x2 + 500),
                top=max(0, y1 - 100),
                bottom=min(768, y2 + 100),
            )
            cx = (x1 + x2) / 2
            cropped_img = region.extract_client_img(self.data.current_client_img)
            mobs_locations = self.get_mobs_positions_in_img(
                cropped_img, self.data.current_mobs
            )

            if len(mobs_locations) >= max(
                self.data.mob_threshold, self.MIN_MOBS_THRESHOLD
            ):
                # Compute "center of mass" of mobs at the character's left and right
                center_x = [rect[0] + rect[2] / 2 for rect in mobs_locations]
                left_x = [rect_x for rect_x in center_x if rect_x < cx]
                right_x = [rect_x for rect_x in center_x if rect_x >= cx]

                minimap_width = self.data.current_minimap.map_area_width
                map_width = self.data.current_map.vr_width

                # Go towards left
                if len(left_x) > len(right_x):
                    avg_dist = sum([abs(rect_x - cx) for rect_x in left_x]) / len(
                        left_x
                    )
                    minimap_dist = min(int(avg_dist * minimap_width / map_width), 10)
                    minimap_x, minimap_y = self.data.current_minimap_position
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    minimum_x = curr_feature.left
                    if curr_feature.avoid_edges:
                        minimum_x += curr_feature.edge_threshold
                    target = (
                        max(minimap_x - minimap_dist, minimum_x),
                        curr_feature.top
                    )
                    return target

                # Go towards right
                else:
                    avg_dist = sum([abs(rect_x - cx) for rect_x in right_x]) / len(
                        right_x
                    )
                    minimap_dist = min(int(avg_dist * minimap_width / map_width), 10)
                    minimap_x, minimap_y = self.data.current_minimap_position
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    maximum_x = curr_feature.right
                    if curr_feature.avoid_edges:
                        maximum_x -= curr_feature.edge_threshold
                    target = (
                        min(minimap_x + minimap_dist, maximum_x),
                        curr_feature.top
                    )
                    return target

        self.data.update_attribute('next_feature')
        return self.data.next_feature.random()


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
                self.data.current_minimap,
            ),
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
                getattr(self.data, "speed_multiplier", 1.0),
            ),
        )
        self.data.create_attribute("has_pathing_attributes", lambda: True)

    def _always_release_keys_on_actions(self):
        actions = self.data.movement_handler.movements_into_action(
            self.data.movements,
            self.data.action_duration,
            getattr(self.data, "speed_multiplier", 1.0),

        )
        if actions is not None:
            for key in actions.keys_held:
                if key not in actions.forced_key_releases:
                    actions.forced_key_releases.append(key)
        return actions
