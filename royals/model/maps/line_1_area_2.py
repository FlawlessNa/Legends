from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import KerningLine1Area2Minimap
from royals.model.mobs import JrWraith
from .base import RoyalsMap


@dataclass
class Line1Area2(RoyalsMap):
    minimap: KerningLine1Area2Minimap = field(default_factory=KerningLine1Area2Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (JrWraith(), ))
