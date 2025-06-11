from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from maple._old.minimaps import KerningLine1Area1Minimap
from maple._old.mobs import Bubbling
from .base import RoyalsMap


@dataclass
class Line1Area1(RoyalsMap):
    minimap: KerningLine1Area1Minimap = field(default_factory=KerningLine1Area1Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (Bubbling(), ))
