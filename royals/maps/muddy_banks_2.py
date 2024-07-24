from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.maps.trend_zone_metropolis import TrendZoneMetropolis
from royals.models_implementations.minimaps import MuddyBanks2Minimap
from royals.models_implementations.mobs import Rodeo
from .base import RoyalsMap


@dataclass
class MuddyBanks2(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: MuddyBanks2Minimap = MuddyBanks2Minimap()
    mobs: tuple[BaseMob] = (
        Rodeo(Box(left=0, right=1024, top=0, bottom=700)),
    )
    path_to_shop: RoyalsMap = field(default_factory=TrendZoneMetropolis)
