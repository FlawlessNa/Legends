from botting.core import BotData
from maple.decision_makers.providers.menus import InventoryMenuProvider


class MenusMixin:
    """
    For the parked `InventoryManager` only; it goes with it (#444).
    """

    data: BotData

    def _create_inventory_menu_attributes(self) -> None:
        """
        The inventory menu's keys (`inventory_menu`, `inventory_menu_displayed`,
        `inventory_menu_extended`, `current_mesos`, `inventory_menu_active_tab`
        and `inventory_space_left`): asks `BotData` for
        `InventoryMenuProvider`, which serves them, unless it is built.
        """
        self.data.build_provider(InventoryMenuProvider)
