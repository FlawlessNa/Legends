import multiprocessing.connection
import multiprocessing.managers
import threading

from botting.core import BotData, ProxyFactory
from botting.screen import Reading
from maple.actions import ensure_ability_menu_displayed
from maple.model.interface import AbilityMenu, InventoryMenu


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
            lambda: menu.is_displayed(self.data.handle, self.data.current_frame.pixels),
            initial_value=False,
        )
        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition)
        )
        self.data.create_or_reconfigure_attribute(
            "available_ap",
            lambda: menu.get_available_ap(
                self.data.handle, self.data.current_frame.pixels
            ),
        )
        self.data.create_or_reconfigure_attribute(
            "speed_multiplier",
            lambda: menu.get_speed(self.data.handle, self.data.current_frame.pixels),
        )
        self.data.create_or_reconfigure_attribute(
            "jump_multiplier",
            lambda: menu.get_jump(self.data.handle, self.data.current_frame.pixels),
        )
        if self.data.has_pathing_attributes:
            # Refresh the Movement Plan with the new speed and jump multipliers.
            # Nothing is compiled before dispatch, so `movements` is the live
            # path's downstream attribute.
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
            lambda: menu.is_displayed(self.data.handle, self.data.current_frame.pixels),
            initial_value=False,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_menu_extended",
            lambda: menu.is_extended(self.data.handle, self.data.current_frame.pixels),
            initial_value=False,
        )
        self.data.create_or_reconfigure_attribute(
            "current_mesos",
            lambda: menu.get_current_mesos(self.data.handle),
            initial_value=None,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_menu_active_tab",
            lambda: menu.get_active_tab(
                self.data.handle, self.data.current_frame.pixels
            ),
            initial_value=None,
        )
        self.data.create_or_reconfigure_attribute(
            "inventory_space_left",
            lambda: menu.get_space_left(
                self.data.handle, self.data.current_frame.pixels
            ),
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
        `status_bar`, a `Reading[StatusBar]` from the bot's one `status_bar_reader`
        and its `current_frame`. `current_frame` is the bot's own, created with
        its refresh threshold in `MapleBot.child_init`, and is left as it is: a
        consumer updates `current_frame` and then `status_bar`, and reads
        `status_bar.status` before `status_bar.value`.

        The DecisionMaker must name `STATUS_BAR` in its `screen_readers`, so
        the reader exists when the bot starts.
        """
        reader = self.data.status_bar_reader
        self.data.create_or_reconfigure_attribute(
            "status_bar", lambda: reader.read(self.data.current_frame)
        )
        self.data.set_feature("has_status_bar_attributes")

    def _create_quick_slots_attributes(self) -> None:
        """
        `quick_slots`, a `Reading[QuickSlots]` from the bot's one
        `quick_slots_reader` and its `current_frame`. Like `status_bar`, a
        consumer updates `current_frame` and then `quick_slots`.

        The DecisionMaker must name `QUICK_SLOTS` in its `screen_readers`, so
        the reader exists when the bot starts.
        """
        reader = self.data.quick_slots_reader
        self.data.create_or_reconfigure_attribute(
            "quick_slots", lambda: reader.read(self.data.current_frame)
        )
        self.data.set_feature("has_quick_slots_attributes")

    def _create_chat_attributes(self) -> None:
        """
        `chat_lines`, a `Reading[list[ChatLine]]` of the lines new since it was
        last updated, from the bot's one `chat_reader` and its `current_frame`.

        It is never refreshed on its own: a consumer updates `current_frame`,
        then `chat_lines`, and each update returns only what is new since the
        one before. Until the first update it holds an `ABSENT` reading, so the
        first update returns every line shown.

        The DecisionMaker must name `CHAT` in its `screen_readers`, so the
        reader exists when the bot starts.
        """
        reader = self.data.chat_reader
        self.data.create_or_reconfigure_attribute(
            "chat_lines",
            lambda: reader.read(self.data.current_frame),
            initial_value=Reading.absent(0.0, "not read yet"),
        )
        self.data.set_feature("has_chat_attributes")
