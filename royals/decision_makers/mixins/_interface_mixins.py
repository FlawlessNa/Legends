import multiprocessing.connection
import multiprocessing.managers

from botting.core import BotData, DecisionMaker
from royals.actions import ensure_ability_menu_displayed
from royals.model.interface import (
    AbilityMenu,
    CharacterStats,
    InventoryMenu,
)


class MenusMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection

    def _create_ap_menu_attributes(self, condition=None):
        menu = AbilityMenu()
        if condition is None:
            condition = DecisionMaker.request_proxy(
                self.metadata, f"{self} - Ability Menu Setup", "Condition"
            )

        self.data.create_attribute("ability_menu", AbilityMenu, initial_value=menu)
        self.data.create_attribute(
            "ability_menu_displayed",
            lambda: menu.is_displayed(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition)
        )
        self.data.create_attribute(
            "available_ap",
            lambda: menu.get_available_ap(
                self.data.handle, self.data.current_client_img
            ),
        )
        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition),
            ensure_displayed=False,
        )

    def _display_kwargs(self, identifier: str, timeout: float, condition=None) -> dict:
        if condition is None:
            condition = DecisionMaker.request_proxy(
                self.metadata, identifier, "Condition"
            )
        return {
            "identifier": identifier,
            "handle": self.data.handle,
            "ign": self.data.ign,
            "pipe": self.pipe,
            "menu": self.data.ability_menu,
            "condition": condition,
            "timeout": timeout,
        }


class UIMixin:
    data: BotData

    def _create_ui_attributes(self):
        stats = CharacterStats()
        self.data.create_attribute(
            "character_job", lambda: stats.get_job(self.data.handle)
        )
        self.data.create_attribute(
            "character_level", lambda: stats.get_level(self.data.handle)
        )
        self.data.create_attribute(
            "current_level_img",
            lambda: stats.level_box.extract_client_img(self.data.current_client_img),
        )
