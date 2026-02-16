from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.maps import Ludibrium
from royals.model.minimaps import PathOfTime1Minimap
from royals.model.mobs import PlatoonChronos
from .base import RoyalsMap


@dataclass
class PathOfTime1(RoyalsMap):
    minimap: PathOfTime1Minimap = field(default_factory=PathOfTime1Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (PlatoonChronos(), ))
    path_to_shop: RoyalsMap = field(default_factory=Ludibrium)
    vr_top: int = -600
    vr_left: int = -885
    vr_bottom: int = 1240
    vr_right: int = 894
