from dataclasses import dataclass, field

from botting.models_abstractions import BaseMob
from royals.model.minimaps import BuddhaMinimap
from royals.model.mobs import DreamyGhost
from .base import RoyalsMap


@dataclass
class EncounterWithTheBuddha(RoyalsMap):
    minimap: BuddhaMinimap = field(default_factory=BuddhaMinimap)
    mobs: tuple[BaseMob] = field(default_factory=lambda: (DreamyGhost(), ))
