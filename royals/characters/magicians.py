from botting.models_abstractions import Skill
from .character import Character


class Magician(Character):
    main_stat = "INT"

    @property
    def skills(self) -> dict[str, Skill]:
        return {
            "Magic Guard": Skill(
                "Magic Guard", "Buff", duration=600, animation_time=0.6
            ),
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
                animation_time=0.6,
                horizontal_screen_range=150,
                vertical_screen_range=150,
                horizontal_minimap_distance=9,
                vertical_minimap_distance=9,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


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
                animation_time=0.6,
                horizontal_screen_range=200,
                vertical_screen_range=125,
                unidirectional=False,
            ),
            "Bless": Skill(
                "Bless",
                "Party Buff",
                animation_time=0.6,
                unidirectional=False,
                duration=200,
            ),
            "Invincible": Skill("Invincible", "Buff", animation_time=0.6, duration=300),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Priest(Cleric):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            **super().skills,
            "Holy Symbol": Skill(
                "Holy Symbol",
                "Party Buff",
                animation_time=2.2,
                unidirectional=False,
                duration=120,
                horizontal_minimap_distance=15,
                _use_by_default=True,
            ),
            "Shining Ray": Skill(
                "Shining Ray",
                "Attack",
                animation_time=1.1,
                horizontal_screen_range=200,
                vertical_screen_range=125,
                unidirectional=False,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Bishop(Priest):
    main_skill = "Genesis"

    @property
    def skills(self) -> dict[str, Skill]:
        return {
            **super().skills,
            "Genesis": Skill(
                "Genesis",
                "Attack",
                animation_time=3,
                unidirectional=False,
                _use_by_default=True,
                horizontal_screen_range=400,
                vertical_screen_range=350,
            ),
            "Maple Warrior": Skill(
                "Maple Warrior",
                "Party Buff",
                animation_time=1.5,
                unidirectional=False,
                _use_by_default=True,
                horizontal_minimap_distance=15,
                duration=300,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)
