from royals.models_implementations.mechanics import RoyalsSkill
from .character import Character


class Magician(Character):
    main_stat = "INT"

    @property
    def skills(self) -> dict[str, RoyalsSkill]:
        return {
            "Magic Guard": RoyalsSkill(
                "Magic Guard", "Buff", duration=600, animation_time=0.6
            ),
            "Magic Claw": RoyalsSkill(
                "Magic Claw",
                "Attack",
                animation_time=0.8,
                horizontal_screen_range=310,
                vertical_screen_range=30,
            ),
            "Teleport": RoyalsSkill(  # Put here since shared across all 2nd job magicians
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
    def skills(self) -> dict[str, RoyalsSkill]:
        return {
            **super().skills,
            "Heal": RoyalsSkill(
                "Heal",
                "Attack",
                animation_time=0.6,
                horizontal_screen_range=200,
                vertical_screen_range=125,
                unidirectional=False,
            ),
            "Bless": RoyalsSkill(
                "Bless",
                "Party Buff",
                animation_time=0.6,
                unidirectional=False,
                duration=200,
            ),
            "Invincible": RoyalsSkill("Invincible", "Buff", animation_time=0.6, duration=300),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Priest(Cleric):
    @property
    def skills(self) -> dict[str, RoyalsSkill]:
        return {
            **super().skills,
            "Holy Symbol": RoyalsSkill(
                "Holy Symbol",
                "Party Buff",
                animation_time=2.2,
                unidirectional=False,
                duration=120,
                horizontal_minimap_distance=10,
                _use_by_default=True,
            ),
            "Shining Ray": RoyalsSkill(
                "Shining Ray",
                "Attack",
                animation_time=1.075,
                horizontal_screen_range=200,
                vertical_screen_range=125,
                unidirectional=False,
            ),
            "Mystic Door": RoyalsSkill(
                "Mystic Door",
                "Utility",
                animation_time=1,  # TODO - Confirm
                unidirectional=False,
                duration=180,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Bishop(Priest):
    main_skill = "Genesis"

    @property
    def skills(self) -> dict[str, RoyalsSkill]:
        return {
            **super().skills,
            "Genesis": RoyalsSkill(
                "Genesis",
                "Attack",
                animation_time=2.75,
                unidirectional=False,
                _use_by_default=True,
                horizontal_screen_range=400,
                vertical_screen_range=375,
            ),
            "Maple Warrior": RoyalsSkill(
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
