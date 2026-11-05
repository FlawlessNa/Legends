from .character import Character
from .maple_skills import MapleBuff, MaplePartyBuff


class Rogue(Character):
    main_stat = "LUK"
    skills = {}  # noqa: RUF012 - the job's skill table, as `Character` declares it

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Assassin(Rogue):
    skills = {  # noqa: RUF012 - the job's skill table, as `Character` declares it
        **Rogue.skills,
        "Haste": MaplePartyBuff(
            "Haste",
            animation_time=0.6,  # TODO - Figure this out
            horizontal_screen_range=100,  # TODO - Figure this out
            vertical_screen_range=100,  # TODO - Figure this out
            duration=200,
            unidirectional=False,
        ),
        "Claw Booster": MapleBuff(
            "Claw Booster",
            animation_time=0.6,  # TODO - Figure this out
            duration=200,
            unidirectional=False,
        ),
    }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)


class Hermit(Assassin):
    skills = {  # noqa: RUF012 - the job's skill table, as `Character` declares it
        **Assassin.skills,
        "Meso Up": MaplePartyBuff(
            "Meso Up",
            animation_time=0.6,  # TODO - Figure this out
            horizontal_screen_range=100,  # TODO - Figure this out
            vertical_screen_range=100,  # TODO - Figure this out
            duration=120,
            unidirectional=False,
        ),
    }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)
