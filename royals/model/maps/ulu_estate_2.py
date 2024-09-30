from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import UluEstate2Minimap
from royals.model.mobs import Slygie, Veetron
from .base import RoyalsMap


@dataclass
class UluEstate2(RoyalsMap):
    minimap: UluEstate2Minimap = field(default_factory=UluEstate2Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (Slygie(), Veetron()))
    # path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
