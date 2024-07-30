from dataclasses import dataclass

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import KampungVillageMinimap
from .base import RoyalsMap


@dataclass
class KampungVillage(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: KampungVillageMinimap = KampungVillageMinimap()
    mobs: tuple[BaseMob] = tuple()
