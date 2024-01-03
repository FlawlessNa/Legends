from dataclasses import dataclass

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.models_implementations.minimaps import MysteriousPath3Minimap
from royals.models_implementations.mobs import SelkieJr, Slimy


@dataclass
class MysteriousPath3(BaseMap):
    detection_box: Box = Box(left=0, right=1024, top=29, bottom=700)
    minimap: MysteriousPath3Minimap = MysteriousPath3Minimap()
    mobs: tuple[BaseMob] = (SelkieJr(Box(left=0, right=1024, top=29, bottom=700)),
                            Slimy(Box(left=0, right=1024, top=29, bottom=700)))
