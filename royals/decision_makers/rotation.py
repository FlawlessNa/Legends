import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from functools import partial, lru_cache

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from royals.model.mechanics import get_to_target
from .mixins import NextTargetMixin, MinimapAttributesMixin, MovementsMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


class Rotation(
    DecisionMaker, NextTargetMixin, MinimapAttributesMixin, MovementsMixin
):
    # TODO - Implement logic to continuously check if character strayed too far from
    #  path to cancel current movements

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        movements_duration: float = 0.75,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get("Teleport")
        self.lock = self.request_proxy(self.metadata, f"{self}", "Lock")

        # Minimap attributes
        self._create_minimap_attributes()
        self.data.current_minimap.generate_grid_template(
            True if self._teleport_skill is not None else False
        )

        # Rotation attributes
        self._create_rotation_attributes()
        self._create_pathing_attributes(
            self.data.ign,
            self.data.handle,
            self._teleport_skill,
            self.data.current_minimap,
            movements_duration,
        )

    async def _decide(self) -> None:
        await asyncio.to_thread(self.lock.acquire)
        logger.log(LOG_LEVEL, f"{self} is deciding.")

        self.data.update_attribute("next_target")
        self.data.update_attribute("action")
        if self.data.action is not None:
            self.pipe.send(self._request(self.data.action))
        else:
            self.lock.release()

        # prev_movements = self.data.get_last_known_value("movements", False)
        # movements = self.data.movements
        # if self._compare_with_previous(movements, prev_movements):
        #     self.pipe.send(self._request(movements))

    def _request(self, inputs: controller.KeyboardInputWrapper) -> ActionRequest:
        return ActionRequest(
            inputs.send,
            f"{self}",
            ign=self.data.ign,
            cancels_itself=True,
            requeue_if_not_scheduled=False,
            callback=self.lock.release,
        )

    # @staticmethod
    # def _compare_with_previous(movements, prev_movements):
    #     """
    #     Compare the new movements with the previous movements.
    #     """
    #     if not movements:
    #         return False
    #     elif prev_movements is not None:
    #         if movements[0].func != prev_movements[0].func:
    #             return True
    #         elif movements[0].args != prev_movements[0].args:
    #             return True
    #     return False

    # @lru_cache
    # def _compute_full_path(
    #     self, current: tuple[int, int], target: tuple[int, int]
    # ) -> list[partial]:
    #     """
    #     Re-calculates the entire path
    #     """
    #     return get_to_target(
    #         current,
    #         target,
    #         self.data.current_minimap,
    #         self.data.handle,
    #         controller.key_binds(self.data.ign)["jump"],
    #         self._teleport_skill,
    #         self.data.ign,
    #     )