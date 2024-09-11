from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import UluEstate1Minimap
from royals.model.mobs import Berserkie, Veetron
from .base import RoyalsMap


@dataclass
class UluEstate1(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: UluEstate1Minimap = field(default_factory=UluEstate1Minimap)
    mobs: tuple[BaseMob] = (
        Berserkie(Box(left=0, right=1024, top=0, bottom=700)),
        Veetron(Box(left=0, right=1024, top=0, bottom=700)),
    )
    # path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
