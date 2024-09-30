from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import LudibriumMinimap
from .base import RoyalsMap


@dataclass
class Ludibrium(RoyalsMap):
    minimap: LudibriumMinimap = field(default_factory=LudibriumMinimap)
    mobs: tuple[BaseMob] = field(default_factory=tuple)
