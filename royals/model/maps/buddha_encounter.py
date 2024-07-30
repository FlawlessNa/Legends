from dataclasses import dataclass

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.model.minimaps import BuddhaMinimap
from royals.model.mobs import DreamyGhost


@dataclass
class EncounterWithTheBuddha(BaseMap):
    detection_box: Box = Box(left=3, right=1027, top=482, bottom=573, name=None)
    minimap: BuddhaMinimap = BuddhaMinimap()
    mobs: tuple[BaseMob] = (DreamyGhost(Box(left=0, right=1024, top=29, bottom=700)),)
