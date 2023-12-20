from dataclasses import field
from .character import Character
from .skills import Skill


class Magician(Character):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            "Magic Guard": Skill(
                "Magic Guard", "Buff", 600, animation_time=0.6
            ),  # TODO - Confirm animation time
            "Magic Claw": Skill(
                "Magic Claw",
                "Attack",
                animation_time=0.8,
                horizontal_screen_range=310,
                vertical_screen_range=30,
            ),
        }

    def __init__(self, ign: str, client_size: str) -> None:
        super().__init__(ign, client_size)


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
                vertical_screen_range=80,
                unidirectional=False
            ),  # TODO - Confirm animation time
        }

    def __init__(self, ign: str, client_size: str) -> None:
        super().__init__(ign, client_size)


class Priest(Cleric):
    pass


class Bishop(Priest):
    pass
