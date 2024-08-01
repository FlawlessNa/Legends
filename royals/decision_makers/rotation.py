import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from functools import partial, lru_cache

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from royals.model.mechanics import get_to_target
from ._mixins import _NextTargetMixin, _MinimapAttributesMixin

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')
LOG_LEVEL = logging.INFO


class Rotation(DecisionMaker, _NextTargetMixin, _MinimapAttributesMixin):
    _throttle = 0.05

    def __init__(
            self,
            metadata: multiprocessing.managers.DictProxy,
            data: BotData,
            pipe: multiprocessing.connection.Connection,
            **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get('Teleport')

        # Minimap attributes
        self._create_minimap_attributes()
        self.data.current_minimap.generate_grid_template(
            True if self._teleport_skill is not None else False
        )

        # Rotation attributes
        self._create_rotation_attributes()
        self.data.create_attribute(
            'movements',
            lambda: self._compute_full_path(
                self.data.current_minimap_position, self.data.next_target
            ),
            threshold=0.01
        )
        self.pipe.send(self._request(self.data.movements))

    async def _decide(self) -> None:
        logger.log(LOG_LEVEL, f"{self} is deciding.")
        self.data.update_attribute('next_target')
        prev_movements = self.data.get_last_known_value('movements', False)
        movements = self.data.movements
        if self._compare_with_previous(movements, prev_movements):
            self.pipe.send(self._request(movements))

    def _request(self, movements: list[partial]) -> ActionRequest:
        return ActionRequest(
            movements[0],
            f'{self}',
            ign=self.data.ign,
            cancels_itself=True,
            requeue_if_not_scheduled=False
        )

    @staticmethod
    def _compare_with_previous(movements, prev_movements):
        """
        Compare the new movements with the previous movements.
        """
        if not movements:
            return False
        elif prev_movements is not None:
            if movements[0].func != prev_movements[0].func:
                return True
            elif movements[0].args != prev_movements[0].args:
                return True
        return False

    @staticmethod
    async def _move(movements: list[partial]) -> callable:
        """
        Returns a callable that will execute each movement.
        """
        for movement in movements:
            await movement()

    @lru_cache
    def _compute_full_path(
        self, current: tuple[int, int], target: tuple[int, int]
    ) -> list[partial]:
        """
        Re-calculates the entire path
        """
        return get_to_target(
            current,
            target,
            self.data.current_minimap,
            self.data.handle,
            controller.key_binds(self.data.ign)["jump"],
            self._teleport_skill,
            self.data.ign
        )

    def _truncate_path(self, current, path):
        """
        Instead of re-calculating full path, use the existing path.
        Look at current position and compute the closest node that is on the path. Then,
        truncate path from that node onwards.
        """
        pass
