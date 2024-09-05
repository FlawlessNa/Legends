from royals.model.mechanics import RoyalsSkill
from .character import Character


class Rogue(Character):
    main_stat = "LUK"
    skills = {}

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Assassin(Rogue):
    skills = {
            **Rogue.skills,
            "Haste": RoyalsSkill(
                "Haste",
                "Party Buff",
                animation_time=0.6,  # TODO - Figure this out
                horizontal_screen_range=100,  # TODO - Figure this out
                vertical_screen_range=100,  # TODO - Figure this out
                horizontal_minimap_distance=10,
                vertical_minimap_distance=10,
                duration=200,
                unidirectional=False,
            ),
            "Claw Booster": RoyalsSkill(
                "Claw Booster",
                "Buff",
                animation_time=0.6,  # TODO - Figure this out
                duration=200,
                unidirectional=False,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Hermit(Assassin):
    skills = {
            **Assassin.skills,
            "Meso Up": RoyalsSkill(
                "Meso Up",
                "Party Buff",
                animation_time=0.6,  # TODO - Figure this out
                horizontal_screen_range=100,  # TODO - Figure this out
                vertical_screen_range=100,  # TODO - Figure this out
                horizontal_minimap_distance=10,
                vertical_minimap_distance=10,
                duration=120,
                unidirectional=False,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)
