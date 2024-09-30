from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.maps.kampung_village import KampungVillage
from royals.model.minimaps import FantasyThemePark1Minimap
from royals.model.mobs import Froscola, JesterScarlion
from .base import RoyalsMap


@dataclass
class FantasyThemePark1(RoyalsMap):
    minimap: FantasyThemePark1Minimap = field(default_factory=FantasyThemePark1Minimap)
    mobs: tuple[BaseMob] = field(
        default_factory=lambda: (Froscola(), JesterScarlion()),
    )
    path_to_shop: RoyalsMap = field(default_factory=KampungVillage)
