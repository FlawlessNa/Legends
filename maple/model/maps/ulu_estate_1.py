from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from maple.model.minimaps import UluEstate1Minimap
from maple.model.mobs import Berserkie, Veetron
from .base import RoyalsMap


@dataclass
class UluEstate1(RoyalsMap):
    minimap: UluEstate1Minimap = field(default_factory=UluEstate1Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (Berserkie(), Veetron()))
    # path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
