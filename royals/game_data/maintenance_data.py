from dataclasses import dataclass, field

from botting.core import BotData as EngineData
from royals.model.characters import Character
from royals.model.interface import AbilityMenu, CharacterStats, InventoryMenu


@dataclass
class MaintenanceData(EngineData):
    character: Character = field(default=None)
    ability_menu: AbilityMenu = field(init=False, repr=False)
    character_stats: CharacterStats = field(init=False, repr=False)
    inventory_menu: InventoryMenu = field(init=False, repr=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            "ability_menu": AbilityMenu,
            "character_stats": CharacterStats,
            "inventory_menu": InventoryMenu,
            **super().args_dict,
        }
