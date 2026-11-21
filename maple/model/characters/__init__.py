from .archers import Archer, Crossbowman, Hunter
from .beginner import Beginner
from .character import Character
from .jobs import JOB_IDS, job_line
from .magicians import (
    Bishop,
    Cleric,
    FPArchMage,
    FPMage,
    FPWizard,
    ILArchMage,
    ILMage,
    ILWizard,
    Magician,
    Priest,
)
from .maple_skills import MapleSkill
from .thiefs import Assassin, Bandit, ChiefBandit, Hermit, Rogue, Shadower
from .warriors import (
    Crusader,
    DarkKnight,
    DragonKnight,
    Fighter,
    Hero,
    Page,
    Paladin,
    Spearman,
    Swordsman,
    WhiteKnight,
)

#: The class of each job in `JOB_IDS`, by the name a profile's
#: `character_class` gives, case aside (`character_class`).
MAPPING: dict[str, type[Character]] = {
    "Beginner": Beginner,
    "Swordsman": Swordsman,
    "Fighter": Fighter,
    "Crusader": Crusader,
    "Hero": Hero,
    "Page": Page,
    "WhiteKnight": WhiteKnight,
    "Paladin": Paladin,
    "Spearman": Spearman,
    "DragonKnight": DragonKnight,
    "DarkKnight": DarkKnight,
    "Magician": Magician,
    "WizardFirePoison": FPWizard,
    "MageFirePoison": FPMage,
    "WizardIceLightning": ILWizard,
    "MageIceLightning": ILMage,
    "Cleric": Cleric,
    "Priest": Priest,
    "Bishop": Bishop,
    "Archer": Archer,
    "Hunter": Hunter,
    "Crossbowman": Crossbowman,
    "Rogue": Rogue,
    "Assassin": Assassin,
    "Hermit": Hermit,
    "Bandit": Bandit,
    "ChiefBandit": ChiefBandit,
    "Shadower": Shadower,
}


def character_class(job: str) -> tuple[str, type[Character]]:
    """
    The job a profile's `character_class` names, case aside, as `MAPPING` names
    it, and its class.

    :raises LookupError: No job has that name.
    """
    for name, class_ in MAPPING.items():
        if name.casefold() == job.casefold():
            return name, class_
    raise LookupError(
        f"no job is named {job!r}; the jobs are {', '.join(sorted(MAPPING))}"
    )


__all__ = [
    "JOB_IDS",
    "MAPPING",
    "Archer",
    "Assassin",
    "Bandit",
    "Beginner",
    "Bishop",
    "Character",
    "ChiefBandit",
    "Cleric",
    "Crossbowman",
    "Crusader",
    "DarkKnight",
    "DragonKnight",
    "FPArchMage",
    "FPMage",
    "FPWizard",
    "Fighter",
    "Hermit",
    "Hero",
    "Hunter",
    "ILArchMage",
    "ILMage",
    "ILWizard",
    "Magician",
    "MapleSkill",
    "Page",
    "Paladin",
    "Priest",
    "Rogue",
    "Shadower",
    "Spearman",
    "Swordsman",
    "WhiteKnight",
    "character_class",
    "job_line",
]
