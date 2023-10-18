from dataclasses import dataclass

from ..in_game_visuals import InGameDynamicVisuals


@dataclass(frozen=True)
class InventoryVisuals(InGameDynamicVisuals):
    handle: int
