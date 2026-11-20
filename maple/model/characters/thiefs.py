from .character import Character


class Rogue(Character):
    """The thief line, whose main stat is LUK."""

    main_stat = "LUK"


class Assassin(Rogue):
    pass


class Hermit(Assassin):
    pass


class Bandit(Rogue):
    pass


class ChiefBandit(Bandit):
    pass


class Shadower(ChiefBandit):
    pass
