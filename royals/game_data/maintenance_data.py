from dataclasses import dataclass, field

from botting.core import GameData
from royals.characters import Character
from royals.interface import AbilityMenu, CharacterStats


@dataclass
class MaintenanceData(GameData):
    character: Character = field(default=None)
    maintenance_checks_enabled: bool = field(init=False, default=True)
    ability_menu: AbilityMenu = field(init=False, repr=False)
    character_stats: CharacterStats = field(init=False, repr=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            'ability_menu': AbilityMenu,
            'character_stats': CharacterStats,
            **super().args_dict
        }
