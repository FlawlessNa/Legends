from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import UluEstate2Minimap
from royals.model.mobs import Slygie, Veetron
from .base import RoyalsMap


@dataclass
class UluEstate2(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: UluEstate2Minimap = field(default_factory=UluEstate2Minimap)
    mobs: tuple[BaseMob] = (
        Veetron(Box(left=0, right=1024, top=0, bottom=700)),
        # Slygie(Box(left=0, right=1024, top=0, bottom=700)),
    )
    # path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
