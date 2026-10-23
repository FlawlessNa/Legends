import functools
import itertools
import logging
import math
import time
from collections.abc import Callable, Iterator, Sequence

import numpy as np

from botting import PARENT_LOG
from botting.core import BotData
from maple.decision_makers.mixins._mob_mixins import MobsHittingMixin
from maple.model.mechanics import (
    MovementHandler,
    compile_movements,
)
from maple.model.mechanics.minimap_creation.minimap_edits_model import MinimapEdits

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class NextTargetMixin:
    """
    Utility function to set next target.
    """

    data: BotData
    # Supplied by MobsHittingMixin, which smart rotation asserts is co-inherited.
    get_mobs_positions_in_img: Callable[..., list[Sequence[int]]]
    BASE_ROTATION_THRESHOLD = 10  # Used for basic rotation mechanism
    SMART_ROTATION_THRESHOLD = 4  # Used for "gravitate towards mobs" rotation mechanism
    TIME_ON_TARGET = 0.75  # Used for "smart rotation" mechanism
    MIN_MOBS_THRESHOLD = 2

    def _create_rotation_attributes(
        self,
        *,
        cycle: Iterator[MinimapEdits] | None = None,
        smart_rotation: bool = False,
        mob_count_threshold: int | None = None,
    ) -> None:

        if smart_rotation is True:
            self.data.set_feature("has_smart_rotation")
            assert mob_count_threshold is not None, (
                "Mob count threshold must be provided for smart rotation."
            )
            self.data.set_static("mob_threshold", mob_count_threshold)

        # If the map has a cycle provided for features, use it
        if self.data.current_minimap.feature_cycle:
            if cycle is None:
                self.data.set_static(
                    "feature_cycle",
                    itertools.cycle(self.data.current_minimap.feature_cycle),
                )
            self.data.create_or_reconfigure_attribute(
                "next_feature",
                lambda: next(self.data.feature_cycle),
            )
            if not self.data.has_smart_rotation:
                self.data.create_or_reconfigure_attribute(
                    "next_target",
                    self._update_next_target_from_cycle,
                    initial_value=self.data.next_feature.random(),
                )
            else:
                self.data.create_or_reconfigure_attribute(
                    "next_target",
                    self._smart_rotation_target,
                    initial_value=self.data.next_feature.random(),
                )
        # If not cycle provided for current map, rotate at random
        else:
            if not self.data.has_smart_rotation:
                self.data.create_or_reconfigure_attribute(
                    "next_target",
                    self._update_next_random_target,
                    initial_value=self.data.current_minimap.random_point(),
                )
            else:
                self.data.create_or_reconfigure_attribute(
                    "next_target",
                    self._smart_rotation_target,
                    initial_value=self.data.current_minimap.random_point(),
                )
            self.data.create_or_reconfigure_attribute(
                "next_feature",
                lambda: self.data.current_minimap.get_feature_containing(
                    self.data.next_target
                ),
            )
        self.data.set_feature("has_rotation_attributes")

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

    def _update_next_random_target(self) -> tuple[int, int]:
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

    def _abandon_current_target(self) -> tuple[int, int]:
        """
        Drop the target the rotation is heading for and pick a different one.

        Movement recovery's **Abandon** rung (`CONTEXT.md` -> Reaction Ladder).
        Both update functions above return the *current* target until the
        character is within threshold of it, which is exactly what keeps a Stuck
        loop stuck: re-deciding cannot change where it is going. So the new target
        is written straight onto the attribute, and each branch picks it with its
        own machinery - advancing the feature cycle where there is one, drawing a
        fresh random point where there is not.

        The draw may of course land back on the same feature. That is not worth
        guarding: the ladder is already at Abandon, so the next symptom escalates.
        :return: The new target.
        """
        if self.data.current_minimap.feature_cycle:
            self.data.update_attribute("next_feature")
            self.data.next_target = self.data.next_feature.random()
        else:
            self.data.next_target = self.data.current_minimap.random_point()
            self.data.update_attribute("next_feature")
        return self.data.next_target

    def _set_fixed_target(self, target: tuple[int, int]) -> None:
        """
        Move to the location where the buffs are cast.
        """
        if self.data.has_rotation_attributes:
            # Overwrite how the next_target attribute is set until the rebuff is done.
            # Snapshot first: the hijack is undone by restoring the rotation owner's
            # exact update function. Re-deriving it with _create_rotation_attributes
            # from here would rebind it to *this* DecisionMaker instead.
            self.data.snapshot_attribute("next_target")
            self.data.reconfigure_attribute(
                "next_target",
                update_function=lambda: target,
            )
            self._reset_flag = True

    def _restore_rotation_target(self) -> None:
        """
        Undoes a next_target hijack, putting back the update function installed by
        whichever DecisionMaker owns the rotation.
        """
        if self.data.has_rotation_attributes:
            self.data.restore_attribute("next_target")

    def _smart_rotation_target(self) -> tuple[int, int]:
        """
        Determines the next target to move towards in a "smart way".
        Uses current on-screen location to get a wide view on the current platform.
        If there are mobs, target the "average" position of those in the direction
        where there are most. Otherwise, move towards the next feature in the cycle.
        :return:
        """
        assert hasattr(self.data, "mob_threshold"), (
            "_mob_threshold attribute must be set."
        )
        assert hasattr(self, "get_mobs_positions_in_img"), (
            f"MobsHittingMixin must be inherited by {self} for smart rotation"
        )
        if not hasattr(self, "_first_time_on_target"):
            self._first_time_on_target = True
        if not hasattr(self, "_last_target_reached_at"):
            self._last_target_reached_at = time.perf_counter()

        if (
            math.dist(self.data.current_minimap_position, self.data.next_target)
            > self.SMART_ROTATION_THRESHOLD
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
        self.data.update_attribute("current_client_img")
        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            shape = self.data.current_client_img.shape
            mask = np.zeros(shape, np.uint8)
            mask[
                max(0, y1 - 100) : min(shape[0], y2 + 100),
                max(0, x1 - 500) : min(shape[1], x2 + 500),
            ] = 255
            mobs_locations = self.get_mobs_positions_in_img(
                self.data.current_client_img, self.data.current_mobs, mask=mask
            )

            cx = (x1 + x2) / 2
            if len(mobs_locations) >= max(
                self.data.mob_threshold, self.MIN_MOBS_THRESHOLD
            ):
                # Compute "center of mass" of mobs at the character's left and right
                center_x = [
                    MobsHittingMixin.box_center(rect)[0] for rect in mobs_locations
                ]
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
                    minimap_x = self.data.current_minimap_position[0]
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    minimum_x = curr_feature.left
                    if curr_feature.avoid_edges:
                        minimum_x += curr_feature.edge_threshold
                    target = (
                        max(minimap_x - minimap_dist, minimum_x),
                        curr_feature.top,
                    )
                    return target

                # Go towards right
                else:
                    avg_dist = sum([abs(rect_x - cx) for rect_x in right_x]) / len(
                        right_x
                    )
                    minimap_dist = min(int(avg_dist * minimap_width / map_width), 10)
                    minimap_x = self.data.current_minimap_position[0]
                    curr_feature = self.data.current_minimap.get_feature_containing(
                        self.data.next_target
                    )
                    maximum_x = curr_feature.right
                    if curr_feature.avoid_edges:
                        maximum_x -= curr_feature.edge_threshold
                    target = (
                        min(minimap_x + minimap_dist, maximum_x),
                        curr_feature.top,
                    )
                    return target

        self.data.update_attribute("next_feature")
        return self.data.next_feature.random()


class MovementsMixin:
    data: BotData
    NO_PATH_FOUND_THRESHOLD: float = 15.0

    def _create_pathing_attributes(
        self,
        duration: float,
        *,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
    ) -> None:
        """
        :param duration: The Action duration cap a Movement Plan is compiled against.
        :param narrow_platform_threshold: Overrides the platform width below which a
            jump or teleport gets its landing direction-stop. `None` leaves
            `MovementHandler`'s default in place, which is what production wants; a
            Trial batch sweeping the precision-movement Knob is the one caller that
            passes anything else.
        :param edge_departure_threshold: Overrides the distance from a platform's end
            within which a jump or teleport gets its pre-departure stop. Same shape
            as `narrow_platform_threshold`.
        """
        self.data.set_static("action_duration", duration)
        self.data.create_or_reconfigure_attribute(
            "movement_handler",
            lambda: MovementHandler(
                self.data.handle,
                self.data.current_minimap,
                self.data.ign,
                self.data.character.skills.get("Teleport"),
                narrow_platform_threshold=narrow_platform_threshold,
                edge_departure_threshold=edge_departure_threshold,
            ),
        )

        self.data.create_or_reconfigure_attribute(
            "path",
            lambda: self.data.movement_handler.compute_path(
                self.data.current_minimap_position,
                self.data.next_target,
                self.data.current_grid,
            ),
            threshold=0.1,
        )
        self.data.create_or_reconfigure_attribute(
            "movements",
            lambda: self.data.movement_handler.path_into_movements(
                self.data.path, self.data.current_grid
            ),
            threshold=0.1,
        )
        # No compiled `action` attribute: nothing is compiled in this process any
        # more. A DecisionMaker decides from `movements` and ships the plan, which
        # Main Process compiles at dispatch against the Held-Keys Ledger (ADR 0002).
        self.data.set_static("always_release_keys", False)
        self.data.set_feature("has_pathing_attributes")

    def _has_movements(self) -> bool:
        """
        Whether the current Movement Plan compiles to anything at all. A plan holding
        nothing but the END_OF_MOVEMENT sentinel produces no Input Sequence - this is
        the live replacement for the old `data.action is not None` check, which could
        only be made by compiling first.
        """
        movements = self.data.movements
        return movements is not None and len(movements) > 1

    def _movement_compiler(self) -> functools.partial:
        """
        Freezes the compile inputs for the current Movement Plan into a picklable
        callable, to be handed to `controller.compile_and_send` inside an
        ActionRequest. Main Process calls it with the Held-Keys Ledger's entry for
        this handle, from inside the focus-lock critical section.

        `MovementHandler` itself cannot travel: its per-instance `lru_cache` wrappers
        are unpicklable, and the grid is only consulted for its speed.
        """
        return functools.partial(
            compile_movements,
            movements=self.data.movements,
            handle=self.data.handle,
            ign=self.data.ign,
            speed=self.data.current_grid.speed,
            teleport=self.data.character.skills.get("Teleport"),
            total_duration=self.data.action_duration,
            always_release=self.data.always_release_keys,
        )
