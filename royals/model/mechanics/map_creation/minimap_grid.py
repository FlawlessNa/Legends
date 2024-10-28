import numpy as np
from dataclasses import dataclass
from enum import IntEnum
from pathfinding.core.grid import Grid
from pathfinding.core.node import GridNode


class ConnectionTypes(IntEnum):
    """
    Enum to hold the different types of connections nodes.
    """
    JUMP_DOWN = 1
    JUMP_LEFT = 2
    JUMP_RIGHT = 3
    JUMP_UP = 4
    FALL_LEFT = 5
    FALL_RIGHT = 6
    FALL_ANY = 7
    JUMP_LEFT_AND_UP = 8
    JUMP_RIGHT_AND_UP = 9
    IN_MAP_PORTAL = 10
    OUT_MAP_PORTAL = 11
    TELEPORT_LEFT = 12
    TELEPORT_RIGHT = 13
    TELEPORT_UP = 14
    TELEPORT_DOWN = 15
    FLASH_JUMP_LEFT = NotImplemented
    FLASH_JUMP_RIGHT = NotImplemented
    FLASH_JUMP_LEFT_AND_UP = NotImplemented
    FLASH_JUMP_RIGHT_AND_UP = NotImplemented


@dataclass
class MinimapNode(GridNode):
    """
    Wrapper around GridNode that retains the type of connections with each node this
    one is connected to.
    """
    pass


class MinimapGrid(Grid):
    """
    Wrapper around Grid that replaces all GridNodes with MinimapNodes.
    """
    def __init__(self, canvas: np.ndarray, grid_id: str = None):
        super().__init__(matrix=canvas, grid_id=grid_id)
        self.grid_id = grid_id
