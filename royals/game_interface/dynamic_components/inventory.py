from dataclasses import dataclass

from ..in_game_visuals import InGameDynamicVisuals


@dataclass(frozen=True)
class InventoryInterface:
    pass


class InventoryVisuals(InventoryInterface, InGameDynamicVisuals):
    pass
