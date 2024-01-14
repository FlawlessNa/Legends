from dataclasses import dataclass

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.models_implementations.minimaps import KerningLine1Area1Minimap
from royals.models_implementations.mobs import Bubbling


@dataclass
class Line1Area1(BaseMap):
    detection_box: Box = Box(left=0, right=1024, top=29, bottom=700)
    minimap: KerningLine1Area1Minimap = KerningLine1Area1Minimap()
    mobs: tuple[BaseMob] = (Bubbling(Box(left=0, right=1024, top=29, bottom=700)),)
