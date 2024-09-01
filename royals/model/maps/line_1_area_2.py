from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.model.minimaps import KerningLine1Area2Minimap
from royals.model.mobs import JrWraith


@dataclass
class Line1Area2(BaseMap):
    detection_box: Box = Box(left=0, right=1024, top=29, bottom=700)
    minimap: KerningLine1Area2Minimap = field(default_factory=KerningLine1Area2Minimap)
    mobs: tuple[BaseMob] = (JrWraith(Box(left=0, right=1024, top=29, bottom=700)),)
