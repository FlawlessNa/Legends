from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import MysteriousPath3Minimap
from royals.model.mobs import SelkieJr, Slimy
from .base import RoyalsMap


@dataclass
class MysteriousPath3(RoyalsMap):
    minimap: MysteriousPath3Minimap = field(default_factory=MysteriousPath3Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (SelkieJr(), Slimy()))
    vr_top: int = -950
    vr_left: int = -1580
    vr_bottom: int = 410
    vr_right: int = 2520
