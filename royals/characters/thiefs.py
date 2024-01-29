from botting.models_abstractions import Skill
from .character import Character


class Rogue(Character):
    main_stat = "LUK"

    @property
    def skills(self) -> dict[str, Skill]:
        return {}

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Assassin(Rogue):
    @property
    def skills(self) -> dict[str, Skill]:
        return {
            **super().skills,
            "Haste": Skill(
                "Haste",
                "Party Buff",
                animation_time=0.6,  # TODO - Figure this out
                horizontal_screen_range=200,  # TODO - Figure this out
                vertical_screen_range=125,  # TODO - Figure this out
                unidirectional=False,
            ),
        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)
