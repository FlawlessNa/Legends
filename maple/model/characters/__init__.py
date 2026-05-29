from .character import Character
from .magicians import Magician, Cleric, Priest, Bishop, FPWizard, FPMage, FPArchMage
from .thiefs import Rogue, Assassin, Hermit
from .maple_skills import MapleSkill, MapleBuff, MaplePartyBuff

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

ALL_BUFFS = dict()
for char in MAPPING.values():
    ALL_BUFFS.update(char.skills)
