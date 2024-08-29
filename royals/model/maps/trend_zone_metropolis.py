from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import TrendZoneMetropolisMinimap
from .base import RoyalsMap


@dataclass
class TrendZoneMetropolis(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: TrendZoneMetropolisMinimap = field(
        default_factory=TrendZoneMetropolisMinimap
    )
    mobs: tuple[BaseMob] = tuple()
