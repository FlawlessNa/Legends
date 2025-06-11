from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from maple._old.minimaps import BuddhaMinimap
from maple._old.mobs import DreamyGhost
from .base import RoyalsMap


@dataclass
class EncounterWithTheBuddha(RoyalsMap):
    minimap: BuddhaMinimap = field(default_factory=BuddhaMinimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (DreamyGhost(), ))
