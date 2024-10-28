from enum import IntEnum


class MovementTypes(IntEnum):
    """
    Enum to hold the different types of movements.
    """
    WALK_LEFT = 1
    WALK_RIGHT = 2
    CLIMB_UP = 3
    CLIMB_DOWN = 4
    JUMP = 5
    JUMP_LEFT = 6
    JUMP_RIGHT = 7
    JUMP_DOWN = 8
    ENTER_PORTAL = 9
    TELEPORT_LEFT = 10
    TELEPORT_RIGHT = 11
    TELEPORT_UP = 12
    TELEPORT_DOWN = 13
    FLASH_JUMP_LEFT = 14
    FLASH_JUMP_RIGHT = 15
