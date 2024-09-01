from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from botting.utilities import Box
from royals.model.minimaps import LudibriumMinimap
from .base import RoyalsMap


@dataclass
class Ludibrium(RoyalsMap):
    detection_box: Box = Box(left=0, right=1024, top=60, bottom=700)
    minimap: LudibriumMinimap = field(default_factory=LudibriumMinimap)
    mobs: tuple[BaseMob] = tuple()
