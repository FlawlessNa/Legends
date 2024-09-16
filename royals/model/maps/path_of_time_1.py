from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.maps import Ludibrium
from royals.model.minimaps import PathOfTime1Minimap
from royals.model.mobs import PlatoonChronos
from .base import RoyalsMap


@dataclass
class PathOfTime1(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: PathOfTime1Minimap = field(default_factory=PathOfTime1Minimap)
    mobs: tuple[BaseMob] = (
        PlatoonChronos(Box(left=0, right=1024, top=29, bottom=700)),
    )
    path_to_shop: RoyalsMap = field(default_factory=Ludibrium)
    vr_top: int = -600
    vr_left: int = -885
    vr_bottom: int = 1240
    vr_right: int = 894
