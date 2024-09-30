from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import KampungVillageMinimap
from .base import RoyalsMap


@dataclass
class KampungVillage(RoyalsMap):
    minimap: KampungVillageMinimap = field(default_factory=KampungVillageMinimap)
    mobs: tuple[BaseMob] = field(default_factory=tuple)
