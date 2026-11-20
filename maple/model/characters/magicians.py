from .character import Character


class Magician(Character):
    """The magician line, whose main stat is INT."""

    main_stat = "INT"


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
    pass


class Priest(Cleric):
    pass


class Bishop(Priest):
    pass
