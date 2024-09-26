from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import MysteriousPath3Minimap
from royals.model.mobs import SelkieJr, Slimy
from .base import RoyalsMap


@dataclass
class MysteriousPath3(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=29, bottom=700)
    minimap: MysteriousPath3Minimap = field(default_factory=MysteriousPath3Minimap)
    mobs: tuple[BaseMob] = (
        SelkieJr(Box(left=0, right=1024, top=29, bottom=700)),
        Slimy(Box(left=0, right=1024, top=29, bottom=700)),
    )
    vr_top: int = -950
    vr_left: int = -1580
    vr_bottom: int = 410
    vr_right: int = 2520
