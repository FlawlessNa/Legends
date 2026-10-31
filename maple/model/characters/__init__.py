from .character import Character
from .magicians import Bishop, Cleric, FPArchMage, FPMage, FPWizard, Magician, Priest
from .maple_skills import MapleBuff, MaplePartyBuff, MapleSkill
from .thiefs import Assassin, Hermit, Rogue

MAPPING = {
    "Magician": Magician,
    "Cleric": Cleric,
    "Priest": Priest,
    "Bishop": Bishop,
    "Rogue": Rogue,
    "Assassin": Assassin,
    "Hermit": Hermit,
    "WizardFirePoison": FPWizard,
    "MageFirePoison": FPMage,
}

__all__ = [
    "MAPPING",
    "Assassin",
    "Bishop",
    "Character",
    "Cleric",
    "FPArchMage",
    "FPMage",
    "FPWizard",
    "Hermit",
    "Magician",
    "MapleBuff",
    "MaplePartyBuff",
    "MapleSkill",
    "Priest",
    "Rogue",
]
