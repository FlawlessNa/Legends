import numpy as np
from functools import cached_property, partial

from ..trigger_based import TriggerBasedGenerator
from botting.core import QueueAction, controller
from botting.utilities import config_reader, take_screenshot
from royals.game_data import MaintenanceData


class DistributeAP(TriggerBasedGenerator):
    generator_type = "Maintenance"

    def __init__(self,
                 data: MaintenanceData,
                 interval: int = 30
                 ) -> None:
        super().__init__(data, interval)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Ability Menu"
        ]
        self._current_lvl_img = self._prev_lvl_img = None

    def __repr__(self):
        return "DistributeAP"

    @property
    def data_requirements(self) -> tuple:
        return "ability_menu", "character_stats"

    @cached_property
    def _offset_box(self) -> tuple[int, int]:
        return self.data.ability_menu.stat_mapper[self.data.character.main_stat]

    def _setup(self) -> QueueAction | None:
        if self._current_lvl_img is None:
            self._current_lvl_img = take_screenshot(
                self.data.handle, self.data.character_stats.level_box
            )
            self._prev_lvl_img = self._current_lvl_img

        if not np.array_equal(self._current_lvl_img, self._prev_lvl_img):
            if not self.data.ability_menu.is_displayed(self.data.handle):
                self._set_status("Idle")
                return QueueAction(
                    identifier="Opening ability menu",
                    priority=1,
                    action=partial(
                        controller.press,
                        self.data.handle,
                        self._key,
                        silenced=True,
                    ),
                    update_game_data={f"{repr(self)}_status": "Setup"}
                )
            self._set_status("Ready")
        else:
            self._update_attributes()
            self._set_status("Done")

    def _update_attributes(self) -> None:
        self._prev_lvl_img = self._current_lvl_img.copy()
        self._current_lvl_img = take_screenshot(
            self.data.handle, self.data.character_stats.level_box
        )

    def _trigger(self) -> QueueAction | None:
        # Called when triggered. Check that there are indeed AP to distribute.
        ap_available = self.data.ability_menu.get_available_ap(self.data.handle)
        if ap_available is None:
            self._fail_count += 1
            return

        if ap_available > 0:
            # If we do, distribute it
            target_box = self.data.ability_menu.get_abs_box(
                self.data.handle, self._offset_box
            )
            target = target_box.random()
            self._set_status("Idle")
            return QueueAction(
                identifier="Distributing AP",
                priority=1,
                action=partial(
                    self._distribute_ap, self.data.handle, target, ap_available
                ),
                update_game_data={f"{repr(self)}_status": "Ready"}
            )
        else:
            self._set_status("Done")

    @staticmethod
    async def _distribute_ap(
        handle: int, target_stat: tuple[int, int], nbr_of_clicks: int = 5
    ):
        await controller.mouse_move(handle, target_stat)
        await controller.click(handle, nbr_times=nbr_of_clicks, delay=0.15)


# class DistributeAP(DecisionGenerator):
#     generator_type = "Maintenance"
#
#     def __init__(self, data: MaintenanceData) -> None:
#         super().__init__(data)
#
#         self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
#             "Ability Menu"
#         ]
#         self._current_lvl_img = self._prev_lvl_img = None
#         self._next_call = time.perf_counter()
#
#     def __repr__(self) -> str:
#         return "DistributeAP"
#
#     @property
#     def data_requirements(self) -> tuple:
#         return "ability_menu", "character_stats"
#
#     @cached_property
#     def _offset_box(self) -> tuple[int, int]:
#         return self.data.ability_menu.stat_mapper[self.data.character.main_stat]
#
#     def _failsafe(self):
#         pass
#
#     def _next(self):
#         if time.perf_counter() < self._next_call:
#             return
#
#         elif self._current_lvl_img is None:
#             self._current_lvl_img = take_screenshot(
#                 self.data.handle, self.data.character_stats.level_box
#             )
#             self._prev_lvl_img = self._current_lvl_img
#             return
#
#         if not np.array_equal(self._current_lvl_img, self._prev_lvl_img):
#             if not self.data.ability_menu.is_displayed(self.data.handle):
#                 self._next_call = time.perf_counter() + 1
#                 return QueueAction(
#                     identifier="Opening ability menu",
#                     priority=1,
#                     action=partial(
#                         controller.press,
#                         self.data.handle,
#                         self._key,
#                         silenced=True,
#                         cooldown=0,
#                     ),
#                 )
#
#             else:
#                 # Start by looking whether we have AP to distribute
#                 ap_available = self.data.ability_menu.get_available_ap(self.data.handle)
#                 if ap_available is not None and ap_available > 0:
#                     # If we do, distribute it
#                     target_box = self.data.ability_menu.get_abs_box(
#                         self.data.handle, self._offset_box
#                     )
#                     target = target_box.random()
#                     self._next_call = time.perf_counter() + 2
#                     return QueueAction(
#                         identifier="Distributing AP",
#                         priority=1,
#                         action=partial(
#                             self._distribute_ap, self.data.handle, target, ap_available
#                         ),
#                     )
#                 else:
#                     self._current_lvl_img = take_screenshot(
#                         self.data.handle, self.data.character_stats.level_box
#                     )
#                     self._prev_lvl_img = self._current_lvl_img
#                     return QueueAction(
#                         identifier="Closing ability menu",
#                         priority=1,
#                         action=partial(
#                             controller.press,
#                             self.data.handle,
#                             self._key,
#                             silenced=True,
#                             cooldown=0,
#                         ),
#                     )
#         else:
#             self._prev_lvl_img = self._current_lvl_img.copy()
#             self._current_lvl_img = take_screenshot(
#                 self.data.handle, self.data.character_stats.level_box
#             )
#             self._next_call = time.perf_counter() + 30
#
#     @staticmethod
#     async def _distribute_ap(
#         handle: int, target_stat: tuple[int, int], nbr_of_clicks: int = 5
#     ):
#         await controller.mouse_move(handle, target_stat)
#         await controller.click(handle, nbr_times=nbr_of_clicks, delay=0.15)
