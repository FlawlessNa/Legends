import asyncio
import itertools
import logging
import math
import multiprocessing as mp
import random

from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, GeneratorUpdate
from royals.engines.generators.base_rotation import RotationGenerator
from royals import RoyalsData
from royals.actions import telecast
from royals.models_implementations.mechanics import RoyalsSkill

logger = logging.getLogger(PARENT_LOG + "." + __name__)


class TelecastRotationGenerator(RotationGenerator):
    generator_type = "Rotation"

    def __init__(
        self,
        data: RoyalsData,
        teleport_skill: RoyalsSkill,
        ultimate: RoyalsSkill,
        mob_threshold: int = 5,
    ) -> None:
        super().__init__(data, ultimate, mob_threshold, teleport_skill)
        self._ultimate = ultimate
        self._target_cycle = itertools.cycle(self.data.current_minimap.feature_cycle)
        if len(self.data.current_minimap.feature_cycle) > 0:
            self.next_feature = random.choice(self.data.current_minimap.feature_cycle)
            self.next_target = self.next_feature.random()
            for _ in range(
                self.data.current_minimap.feature_cycle.index(self.next_feature) + 1
            ):
                next(self._target_cycle)
        else:
            self.next_target = self.data.current_minimap.random_point()
            self.next_feature = self.data.current_minimap.get_feature_containing(
                self.next_target
            )

    def _set_next_target(self):
        if math.dist(self.data.current_minimap_position, self.next_target) > 10:
            pass
        else:
            if len(self.data.current_minimap.feature_cycle) > 0:
                self.next_feature = next(self._target_cycle)
                self.next_target = self.next_feature.random()
            else:
                self.next_target = self.data.current_minimap.random_point()
                self.next_feature = self.data.current_minimap.get_feature_containing(
                    self.next_target
                )

    def _next(self) -> QueueAction | None:
        """
        Overwrites base rotation to combine mob hitting with telecasting, if appropriate
        """
        if getattr(self.data, "next_target", None) is not None:
            self.next_target = self.data.next_target
        else:
            self._set_next_target()

        hit_mobs = self._mobs_hitting()
        if hit_mobs is not None:
            # Check for telecast
            if len(self.actions) == 0 or self.actions[0].func.__name__ != "teleport":
                # If first move isn't a teleport, simply cast skill instead
                return hit_mobs
            else:
                # If first move is teleport, replace by telecast and keep teleporting
                direction = self.actions[0].args[-2]
                res = partial(
                    telecast,
                    self.data.handle,
                    self.data.ign,
                    direction,
                    self._teleport,
                    self._ultimate,
                )
                self.blocked = True
                # directions = []
                # while self.actions and self.actions[0].func.__name__ == "teleport":
                #     next_action = self.actions.pop(0)
                #     directions.extend(
                #         [next_action.args[-2]] * next_action.keywords["num_times"]
                #     )
                # res = partial(
                #     telecast,
                #     self.data.handle,
                #     self.data.ign,
                #     directions,
                #     self._teleport,
                #     self._ultimate,
                # )

                updater = GeneratorUpdate(
                    game_data_kwargs={"available_to_cast": True},
                    generator_id=id(self), generator_kwargs={"blocked": False}
                )
                return QueueAction(
                    identifier=self.__class__.__name__,
                    priority=98,
                    action=res,
                    update_generators=updater
                )
        else:
            return self._rotation()
