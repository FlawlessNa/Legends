from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.maps.trend_zone_metropolis import TrendZoneMetropolis
from royals.model.minimaps import MuddyBanks2Minimap
from royals.model.mobs import Rodeo
from .base import RoyalsMap


@dataclass
class MuddyBanks2(RoyalsMap):
    minimap: MuddyBanks2Minimap = field(default_factory=MuddyBanks2Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (Rodeo(), ))
    path_to_shop: RoyalsMap = field(default_factory=TrendZoneMetropolis)
