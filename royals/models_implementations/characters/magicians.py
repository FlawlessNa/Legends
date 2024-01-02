from dataclasses import field
from .character import Character
from .skills import Skill


class Magician(Character):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            "Magic Guard": Skill(
                "Magic Guard", "Buff", 600, animation_time=0.6
            ),  # TODO - Figure real animation time
            "Magic Claw": Skill(
                "Magic Claw",
                "Attack",
                animation_time=0.8,
                horizontal_screen_range=310,
                vertical_screen_range=30,
            ),
            "Teleport": Skill(  # Put here since shared across all 2nd job magicians
                "Teleport",
                "Movement",
                animation_time=0.5,  # TODO - Figure real animation time
                horizontal_screen_range=150,
                vertical_screen_range=150,
                horizontal_minimap_distance=9,
                vertical_minimap_distance=9,
            )
        }

    def __init__(self, ign: str, section: str, client_size: str) -> None:
        super().__init__(ign, section, client_size)


class ILWizard(Magician):
    pass


class ILMage(ILWizard):
    pass


class ILArchMage(ILMage):
    pass


class FPWizard(Magician):
    pass


class FPMage(FPWizard):
    pass


class FPArchMage(FPMage):
    pass


class Cleric(Magician):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            **super().skills,
            "Heal": Skill(
                "Heal",
                "Attack",
                animation_time=0.25,
                horizontal_screen_range=200,
                vertical_screen_range=125,
                unidirectional=False
            ),  # TODO - Confirm animation time
            "Bless": Skill(
                "Bless",
                "Party Buff",
                animation_time=0.5,  # TODO - Confirm animation time
                unidirectional=False,
                duration=200
            ),
            "Invincible": Skill(
                "Invincible",
                "Buff",
                animation_time=0.5,  # TODO - Confirm animation time
                duration=300
            )
        }

    def __init__(self, ign: str, section: str, client_size: str) -> None:
        super().__init__(ign, section, client_size)


class Priest(Cleric):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            **super().skills,
            "Holy Symbol": Skill(
                "Holy Symbol",
                "Party Buff",
                animation_time=0.75,  # TODO - Confirm animation time
                unidirectional=False,
                duration=90
            ),
        }

    def __init__(self, ign: str, section: str, client_size: str) -> None:
        super().__init__(ign, section, client_size)


class Bishop(Priest):
    pass
