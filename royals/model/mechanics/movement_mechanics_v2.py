import logging
from enum import IntEnum
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG
from .map_creation.minimap_grid import MinimapNode, MinimapGrid

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET
DEBUG = True


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


class MovementHandler:
    def __init__(self) -> None:
        pass

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int], grid: MinimapGrid
    ) -> tuple[MinimapNode, ...]:
        finder = DijkstraFinder() if grid.has_portals else AStarFinder()
        start_node = grid.node(*start)
        end_node = grid.node(*end)
        path = finder.find_path(start_node, end_node, grid)
        grid.cleanup()
        return path
