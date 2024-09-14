from royals.model.mechanics import RoyalsSkill, RoyalsPartyBuff, RoyalsBuff
from .character import Character


class Rogue(Character):
    main_stat = "LUK"
    skills = {}

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Assassin(Rogue):
    skills = {
            **Rogue.skills,
            "Haste": RoyalsPartyBuff(
                "Haste",
                animation_time=0.6,  # TODO - Figure this out
                horizontal_screen_range=100,  # TODO - Figure this out
                vertical_screen_range=100,  # TODO - Figure this out
                duration=200,
                unidirectional=False,
                match_template_threshold=0.5,
                match_icon_threshold=0.74,
            ),
            "Claw Booster": RoyalsBuff(
                "Claw Booster",
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
            "Meso Up": RoyalsPartyBuff(
                "Meso Up",
                animation_time=0.6,  # TODO - Figure this out
                horizontal_screen_range=100,  # TODO - Figure this out
                vertical_screen_range=100,  # TODO - Figure this out
                duration=120,
                unidirectional=False,
                match_template_threshold=0.5,
                match_icon_threshold=0.75,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)
