from .character import Character


class Swordsman(Character):
    """
    A first-job Swordsman: no skill table yet, so no buff, attack or teleport is
    planned for it. The class a profile names (`character_class: Swordsman`) for a
    character that moves and does nothing else, such as a calibration sitting's.
    """

    main_stat = "STR"
    skills = {}  # noqa: RUF012 - the job's skill table, as `Character` declares it
