from botting.core import BotData
from royals.model.interface import (
    AbilityMenu,
    CharacterStats,
    InventoryMenu,
)


class MenusMixin:
    data: BotData

    def _create_ap_menu_attributes(self):
        menu = AbilityMenu()
        self.data.create_attribute(
            'ability_menu',
        )


class UIMixin:
    data: BotData