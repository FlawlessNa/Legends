from abc import ABC
from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseMob
from royals.model.mechanics import MinimapPathingMechanics


@dataclass
class RoyalsMap(BaseMap, ABC):
    """
    Base Map class for Royals, where the minimap is a MinimapPathingMechanics instance.
    """
    mobs: tuple[BaseMob]
    minimap: MinimapPathingMechanics
    path_to_shop: "RoyalsMap" = field(default=None)
    vr_left: int = field(default=None)
    vr_right: int = field(default=None)
    vr_top: int = field(default=None)
    vr_bottom: int = field(default=None)

    @property
    def vr_width(self) -> int:
        return self.vr_right - self.vr_left

    @property
    def vr_height(self) -> int:
        return self.vr_bottom - self.vr_top
