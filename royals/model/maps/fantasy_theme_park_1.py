from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.maps.kampung_village import KampungVillage
from royals.model.minimaps import FantasyThemePark1Minimap
from royals.model.mobs import Froscola, JesterScarlion
from .base import RoyalsMap


@dataclass
class FantasyThemePark1(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: FantasyThemePark1Minimap = field(default_factory=FantasyThemePark1Minimap)
    mobs: tuple[BaseMob] = (
        Froscola(Box(left=0, right=1024, top=0, bottom=700)),
        JesterScarlion(Box(left=0, right=1024, top=0, bottom=700)),
    )
    path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
