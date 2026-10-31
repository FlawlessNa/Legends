import multiprocessing.connection
import multiprocessing.managers
import threading

from botting.core import BotData, ProxyFactory
from botting.screen import frame_source
from maple.actions import ensure_ability_menu_displayed
from maple.model.interface import (
    AbilityMenu,
    InventoryMenu,
    LargeClientChatFeed,
)
from maple.screen.status_bar import StatusBarReader


class MenusMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection
    _proxies: ProxyFactory

    def _create_ap_menu_attributes(
        self, condition: threading.Condition | None = None
    ) -> None:
        menu = AbilityMenu()
        if condition is None:
            condition = self._proxies.instance(
                f"{self} - Ability Menu Setup", "Condition"
            )

        self.data.set_static("ability_menu", menu)
        self.data.create_or_reconfigure_attribute(
            "ability_menu_displayed",
            lambda: menu.is_displayed(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition)
        )
        self.data.create_or_reconfigure_attribute(
            "available_ap",
            lambda: menu.get_available_ap(
                self.data.handle, self.data.current_client_img
            ),
        )
        self.data.create_or_reconfigure_attribute(
            "speed_multiplier",
            lambda: menu.get_speed(self.data.handle, self.data.current_client_img),
        )
        self.data.create_or_reconfigure_attribute(
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
            # Refresh the Movement Plan against the regenerated grid. This used to
            # refresh the compiled `action`; nothing is compiled before dispatch any
            # more, so `movements` is the live path's downstream attribute.
            self.data.update_attribute("movements")

        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition),
            ensure_displayed=False,
        )
        self.data.set_feature("has_ap_menu_attributes")

    def _create_inventory_menu_attributes(
        self, condition: threading.Condition | None = None
    ) -> None:
        menu = InventoryMenu()
        condition = condition or getattr(self, "_condition", None)
        if condition is None:
            condition = self._proxies.instance(
                f"{self} - Inventory Menu Setup", "Condition"
            )

        self.data.set_static("inventory_menu", menu)
        self.data.create_or_reconfigure_attribute(
            "inventory_menu_displayed",
            lambda: menu.is_displayed(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_menu_extended",
            lambda: menu.is_extended(self.data.handle, self.data.current_client_img),
            initial_value=False,
        )
        self.data.create_or_reconfigure_attribute(
            "current_mesos",
            lambda: menu.get_current_mesos(self.data.handle),
            initial_value=None,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_menu_active_tab",
            lambda: menu.get_active_tab(self.data.handle, self.data.current_client_img),
            initial_value=None,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_space_left",
            lambda: menu.get_space_left(self.data.handle, self.data.current_client_img),
            initial_value=menu.total_slots,
        )
        self.data.set_feature("has_inventory_menu_attributes")

    def _display_kwargs(
        self,
        identifier: str,
        timeout: float,
        condition: threading.Condition | None = None,
    ) -> dict:
        if condition is None:
            condition = self._proxies.instance(identifier, "Condition")
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

    def _create_status_bar_attributes(self) -> None:
        """
        `current_frame` and `status_bar` (a `Reading[StatusBar]`). A consumer
        updates `current_frame` first, then `status_bar`, and reads
        `status_bar.status` before `status_bar.value`.

        The DecisionMaker must name `STATUS_BAR` in its `screen_readers`, so
        the sprites are loaded when the bot starts.
        """
        reader = StatusBarReader(self.data.reader_sprites, self.data.frame_check)
        self.data.create_or_reconfigure_attribute(
            "current_frame", lambda: frame_source().grab(self.data.handle)
        )
        self.data.create_or_reconfigure_attribute(
            "status_bar", lambda: reader.read(self.data.current_frame)
        )
        self.data.set_feature("has_status_bar_attributes")

    def _create_chat_feed_attributes(self) -> None:
        feed = LargeClientChatFeed()
        self.data.set_static("chat_feed", feed)
        self.data.create_or_reconfigure_attribute(
            "chat_feed_displayed", lambda: feed.is_displayed(self.data.handle)
        )
        # TODO - Finish creating other attributes
        self.data.set_feature("has_chat_feed_attributes")
