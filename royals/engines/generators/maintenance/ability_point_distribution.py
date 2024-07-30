import asyncio
import logging
import numpy as np
import time
from functools import cached_property, partial

from botting import PARENT_LOG, controller
from botting.core import GeneratorUpdate, QueueAction
from botting.utilities import config_reader
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class DistributeAP(IntervalBasedGenerator):
    generator_type = "Maintenance"

    def __init__(
        self, data: MaintenanceData, interval: int = 30, deviation: int = 0
    ) -> None:
        super().__init__(data, interval, deviation)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Ability Menu"
        ]
        self._current_lvl_img = self._prev_lvl_img = None

    def __repr__(self):
        return f"{self.__class__.__name__}({self.data.ign})"

    @property
    def initial_data_requirements(self) -> tuple:
        return "ability_menu", "character_stats"

    def _update_continuous_data(self) -> None:
        if self._current_lvl_img is None and self._prev_lvl_img is None:
            self._current_lvl_img = (
                self.data.character_stats.level_box.extract_client_img(
                    self.data.current_client_img
                )
            )
            self._prev_lvl_img = self._current_lvl_img.copy()
        elif self._current_lvl_img is None:
            self._current_lvl_img = (
                self.data.character_stats.level_box.extract_client_img(
                    self.data.current_client_img
                )
            )
        elif self._prev_lvl_img is None:
            raise NotImplementedError
        else:
            self._prev_lvl_img = self._current_lvl_img.copy()
            self._current_lvl_img = (
                self.data.character_stats.level_box.extract_client_img(
                    self.data.current_client_img
                )
            )

    def _failsafe(self) -> QueueAction | None:
        """
        If the images are the same, ensure the ability menu is not displayed.
        :return:
        """
        if np.array_equal(self._current_lvl_img, self._prev_lvl_img):
            if self.data.ability_menu.is_displayed(
                self.data.handle, self.data.current_client_img
            ):
                return self._toggle_ability_menu()

    def _exception_handler(self, e: Exception) -> None:
        if isinstance(e, TypeError):
            if self._error_counter < 5:
                logger.error(
                    f"TypeError in {self}: {e}, attempt {self._error_counter}."
                )
                self._current_lvl_img = None
                return
        raise e

    def _next(self) -> QueueAction | None:
        """
        If lvl box has changed, open up the inventory menu and read how many AP are
        available. If > 0, distribute those points.
        :return:
        """
        if not np.array_equal(self._current_lvl_img, self._prev_lvl_img):
            if not self.data.ability_menu.is_displayed(
                self.data.handle, self.data.current_client_img
            ):
                self._current_lvl_img = None
                return self._toggle_ability_menu()
            else:
                # Menu is displayed, check if there are AP to distribute, 5 attempts
                ap_available = self.data.ability_menu.get_available_ap(
                    self.data.handle, self.data.current_client_img
                )
                if ap_available > 0:
                    self._current_lvl_img = None
                    logger.info(f"{self} will distribute {ap_available} AP.")
                    return self._distribute_ap(ap_available)
                else:
                    logger.info(f"No more AP to distribute for {self}.")
                    return self._toggle_ability_menu()
        else:
            self._next_call = time.perf_counter() + self.interval

    @cached_property
    def _offset_box(self) -> tuple[int, int]:
        return self.data.ability_menu.stat_mapper[self.data.character.main_stat]

    def _toggle_ability_menu(self) -> QueueAction:
        self.blocked = True
        return QueueAction(
            identifier="Toggling ability menu",
            priority=1,
            action=partial(
                controller.press,
                self.data.handle,
                self._key,
                silenced=True,
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={"blocked": False},
            ),
        )

    def _distribute_ap(self, nbr_of_clicks: int = 5):
        target_box = self.data.ability_menu.get_abs_box(
            self.data.handle, self._offset_box
        )
        target = target_box.random()
        self.blocked = True
        return QueueAction(
            identifier="Distributing AP",
            priority=1,
            action=partial(
                self._move_and_click, self.data.handle, target, nbr_of_clicks
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={"blocked": False},
            ),
        )

    @staticmethod
    async def _move_and_click(handle, location, num_times):
        await controller.mouse_move(handle, location)
        await controller.click(handle, nbr_times=num_times, delay=0.15)

    @staticmethod
    async def _toggle_menu(handle: int, key: str):
        await controller.press(handle, key, silenced=True)
        await asyncio.sleep(0.25)
