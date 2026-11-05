import logging
import multiprocessing.connection
import multiprocessing.managers
import threading

from botting import PARENT_LOG
from botting.core import BotData, ProxyFactory
from botting.screen import Reading, Status
from maple.actions import ensure_ability_menu_displayed
from maple.model.interface import InventoryMenu

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MenusMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection
    _proxies: ProxyFactory

    def _create_ap_menu_attributes(
        self, condition: threading.Condition | None = None
    ) -> None:
        """
        `stat_window`, a `Reading[StatWindow]` from the bot's one
        `stat_window_reader` and its `current_frame`; consumers update
        `current_frame`, then `stat_window`, and read its `.status` before its
        `.value`.

        Opens the stat window once, reads speed and jump from its Detail panel
        into `speed_multiplier` and `jump_multiplier`, and closes it. When they
        can't be read (Detail not open, or the reading not `READ`), they keep
        the profile's values, and that is logged.

        The DecisionMaker must name `STAT_WINDOW` in its `screen_readers`, so
        the reader exists when the bot starts.
        """
        reader = self.data.stat_window_reader
        if condition is None:
            condition = self._proxies.instance(
                f"{self} - Ability Menu Setup", "Condition"
            )

        self.data.create_or_reconfigure_attribute(
            "stat_window",
            lambda: reader.read(self.data.current_frame),
            initial_value=Reading.absent(0.0, "not read yet"),
        )
        ensure_ability_menu_displayed(
            **self._display_kwargs(f"{self} - Ability Menu Setup", 2.0, condition)
        )
        self.data.update_attributes("current_frame", "stat_window")
        reading = self.data.stat_window
        if (
            reading.status is Status.READ
            and reading.value.speed is not None
            and reading.value.jump is not None
        ):
            self.data.set_static("speed_multiplier", reading.value.speed / 100)
            self.data.set_static("jump_multiplier", reading.value.jump / 100)
        else:
            logger.warning(
                "%s can't read speed and jump from the stat window (%s: %s); "
                "keeping %.2f and %.2f.",
                self,
                reading.status.name,
                reading.detail or "Detail not open",
                self.data.speed_multiplier,
                self.data.jump_multiplier,
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
            "reader": self.data.stat_window_reader,
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
