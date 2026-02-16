import multiprocessing.connection
import multiprocessing.managers

from botting.core import BotData, DecisionMaker
from royals.actions import ensure_ability_menu_displayed
from royals.model.interface import (
    AbilityMenu,
    CharacterStats,
    InventoryMenu,
    LargeClientChatFeed
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
        self.data.create_attribute(
            "speed_multiplier",
            lambda: menu.get_speed(self.data.handle, self.data.current_client_img),
        )
        self.data.create_attribute(
            "jump_multiplier",
            lambda: menu.get_jump(self.data.handle, self.data.current_client_img),
        )
        # Refresh minimap grid with new speed and jump multipliers
        if self.data.has_minimap_attributes:
            self.data.current_minimap.generate_grid_template(
                self.data.character.skills.get("Teleport") is not None,
                self.data.speed_multiplier,
                self.data.jump_multiplier,
            )

        if self.data.has_pathing_attributes:
            self.data.update_attribute("action")

        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition),
            ensure_displayed=False,
        )
        self.data.create_attribute("has_ap_menu_attributes", lambda: True)

    def _create_inventory_menu_attributes(self, condition=None):
        menu = InventoryMenu()
        condition = condition or getattr(self, "_condition", None)
        if condition is None:
            condition = DecisionMaker.request_proxy(
                self.metadata, f"{self} - Inventory Menu Setup", "Condition"
            )

        self.data.create_attribute("inventory_menu", InventoryMenu, initial_value=menu)
        self.data.create_attribute(
            "inventory_menu_displayed",
            lambda: menu.is_displayed(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        self.data.create_attribute(
            "inventory_menu_extended",
            lambda: menu.is_extended(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        self.data.create_attribute(
            "current_mesos",
            lambda: menu.get_current_mesos(self.data.handle),
            initial_value=None,
        )
        self.data.create_attribute(
            "inventory_menu_active_tab",
            lambda: menu.get_active_tab(self.data.handle, self.data.current_client_img),
            initial_value=None,
        )
        self.data.create_attribute(
            "inventory_space_left",
            lambda: menu.get_space_left(self.data.handle, self.data.current_client_img),
            initial_value=menu.total_slots,
        )
        self.data.create_attribute("has_inventory_menu_attributes", lambda: True)

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
        self.data.create_attribute("has_ui_attributes", lambda: True)

    def _create_chat_feed_attributes(self) -> None:
        feed = LargeClientChatFeed()
        self.data.create_attribute("chat_feed", LargeClientChatFeed, initial_value=feed)
        self.data.create_attribute(
            "chat_feed_displayed", lambda: feed.is_displayed(self.data.handle)
        )
        # TODO - Finish creating other attributes
        self.data.create_attribute("has_chat_feed_attributes", lambda: True)
