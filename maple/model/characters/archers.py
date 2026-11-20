from .character import Character


class Archer(Character):
    """The bowman line, whose main stat is DEX."""

    main_stat = "DEX"


class Hunter(Archer):
    pass


class Crossbowman(Archer):
    pass
