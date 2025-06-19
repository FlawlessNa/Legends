from re import match

from .maple_skills import MapleSkill, MapleBuff, MaplePartyBuff
from .character import Character


class Magician(Character):
    main_stat = "INT"
    skills = {
        "Magic Guard": MapleBuff(
            "Magic Guard",
            duration=600,
            animation_time=0.6,
            match_template_threshold=0.61,
            match_icon_threshold=0.80,
        ),
        "Magic Claw": MapleSkill(
            "Magic Claw",
            "Attack",
            animation_time=0.8,
            horizontal_screen_range=310,
            vertical_screen_range=30,
        ),
        "Teleport": MapleSkill(  # Put here since shared across all 2nd job magicians
            "Teleport",
            "Movement",
            animation_time=0.6,
            horizontal_screen_range=150,
            vertical_screen_range=150,
        ),
    }


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
    skills = {
        **Magician.skills,
        "Heal": MapleSkill(
            "Heal",
            "Attack",
            animation_time=0.6,
            horizontal_screen_range=300,
            vertical_screen_range=200,
            unidirectional=False,
        ),
        "Bless": MaplePartyBuff(
            "Bless",
            animation_time=0.6,
            unidirectional=False,
            duration=200,
            horizontal_screen_range=300,
            vertical_screen_range=200,
        ),
        "Invincible": MapleBuff(
            "Invincible",
            animation_time=0.6,
            duration=300       ,
            match_template_threshold=0.68,
            match_icon_threshold=0.81,
        ),
    }


class Priest(Cleric):
    skills = {
        **Cleric.skills,
        "Holy Symbol": MaplePartyBuff(
            "Holy Symbol",
            animation_time=18 * 0.085,  # TODO - Confirm
            unidirectional=False,
            duration=120,
            horizontal_screen_range=300,
            vertical_screen_range=200,
            _use_by_default=True,
            match_template_threshold=0.675,
            match_icon_threshold=0.79,
        ),
        "Shining Ray": MapleSkill(
            "Shining Ray",
            "Attack",
            animation_time=11 * 0.095,
            horizontal_screen_range=170,
            vertical_screen_range=50,
            unidirectional=False,
        ),
        "Mystic Door": MapleSkill(
            "Mystic Door",
            "Utility",
            animation_time=0.6,  # TODO - Confirm
            unidirectional=False,
            duration=180,
        ),
        "Dispel": MapleSkill(
            "Dispel",
            "Utility",
            animation_time=0.9,  # TODO - Confirm
            horizontal_screen_range=300,
            vertical_screen_range=225,
            unidirectional=False,
        ),
    }


class Bishop(Priest):
    main_skill = "Genesis"
    skills = {
        **Priest.skills,
        "Genesis": MapleSkill(
            "Genesis",
            "Attack",
            animation_time=2.6,
            unidirectional=False,
            _use_by_default=True,
            horizontal_screen_range=400,
            vertical_up_screen_range=350,
            vertical_down_screen_range=250,
        ),
        "Maple Warrior": MaplePartyBuff(
            "Maple Warrior",
            animation_time=0.06 * 24,
            unidirectional=False,
            _use_by_default=True,
            horizontal_screen_range=400,
            vertical_screen_range=300,
            duration=300,
            match_template_threshold=0.59,
            match_icon_threshold=0.80,
        ),
        "Resurrection": MapleSkill(
            "Resurrection",
            "Utility",
            animation_time=0.12 * 21,
            horizontal_screen_range=400,
            vertical_up_screen_range=350,
            vertical_down_screen_range=250,
            unidirectional=False,
            cooldown=1800,
        ),
        "Holy Shield": MapleBuff(
            "Holy Shield",
            animation_time=0.06 * 18,
            duration=40,
            cooldown=120,
            horizontal_screen_range=400,
            vertical_screen_range=300,
        ),
    }
