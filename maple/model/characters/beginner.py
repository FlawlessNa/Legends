from .character import Character


class Beginner(Character):
    """A character before its first job advancement. A beginner has no main
    stat of its own: STR is assumed, as most first jobs need it."""

    main_stat = "STR"
