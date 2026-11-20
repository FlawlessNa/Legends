from .character import Character


class Swordsman(Character):
    """
    The warrior line, whose main stat is STR. A job needs no more than its class:
    its skills come from the client's files, for the names its `Skill Keys` give
    (`maple_skills.character_skills`).
    """

    main_stat = "STR"


class Fighter(Swordsman):
    pass


class Crusader(Fighter):
    pass


class Hero(Crusader):
    pass


class Page(Swordsman):
    pass


class WhiteKnight(Page):
    pass


class Paladin(WhiteKnight):
    pass


class Spearman(Swordsman):
    pass


class DragonKnight(Spearman):
    pass


class DarkKnight(DragonKnight):
    pass
