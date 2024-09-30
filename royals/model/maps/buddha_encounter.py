from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseMob
from royals.model.minimaps import BuddhaMinimap
from royals.model.mobs import DreamyGhost


@dataclass
class EncounterWithTheBuddha(BaseMap):
    minimap: BuddhaMinimap = field(default_factory=BuddhaMinimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (DreamyGhost(), ))
