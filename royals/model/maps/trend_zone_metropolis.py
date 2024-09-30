from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import TrendZoneMetropolisMinimap
from .base import RoyalsMap


@dataclass
class TrendZoneMetropolis(RoyalsMap):
    minimap: TrendZoneMetropolisMinimap = field(
        default_factory=TrendZoneMetropolisMinimap
    )
    mobs: tuple[BaseMob] = field(default_factory=tuple)
