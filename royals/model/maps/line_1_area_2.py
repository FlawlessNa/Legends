from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseMob
from royals.model.minimaps import KerningLine1Area2Minimap
from royals.model.mobs import JrWraith


@dataclass
class Line1Area2(BaseMap):
    minimap: KerningLine1Area2Minimap = field(default_factory=KerningLine1Area2Minimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (JrWraith(), ))
