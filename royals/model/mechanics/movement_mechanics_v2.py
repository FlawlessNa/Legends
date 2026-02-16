import cv2
import logging
import numpy as np
from enum import IntEnum
from functools import lru_cache
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG
from .minimap_mechanics import MinimapConnection, MinimapPathingMechanics, MinimapNode
from .royals_skill import RoyalsSkill

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET
DEBUG = True

class Moves(IntEnum):
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


class Movements:
    def __init__(
        self,
        ign: str,
        handle: int,
        teleport: RoyalsSkill | None,
        minimap: MinimapPathingMechanics,
    ):
        self.ign = ign
        self.handle = handle
        self.teleport = teleport
        self.minimap = minimap
        self.finder = AStarFinder() if not minimap.grid.portals else DijkstraFinder()

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> tuple[MinimapNode, ...]:
        try:
            path = self._compute_path(start, end)
            self._run_debug(start, end, path)
            return tuple(path)
        except Exception as e:
            logger.error(f"Failed to compute path from {start} to {end}: {e}")
            return ()

    @lru_cache
    def _compute_path(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> list[MinimapNode]:
        start_node = self.minimap.grid.node(*start)
        end_node = self.minimap.grid.node(*end)
        path, _ = self.finder.find_path(start_node, end_node, self.minimap.grid)
        self.minimap.grid.cleanup()
        return path

    def _run_debug(
        self, start: tuple[int, int], end: tuple[int, int], path: list[MinimapNode]
    ) -> None:
        if not DEBUG:
            return
        canvas = np.zeros(
            (self.minimap.map_area_height, self.minimap.map_area_width),
            dtype=np.uint8,
        )
        canvas = self.minimap._preprocess_img(canvas)
        path_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
        cv2.drawMarker(
            path_img, (start[0], start[1]), (0, 0, 255), cv2.MARKER_CROSS, markerSize=3
        )
        cv2.drawMarker(
            path_img, (end[0], end[1]), (255, 0, 0), cv2.MARKER_CROSS, markerSize=3
        )
        for node in path:
            path_img[node.y, node.x] = (0, 255, 0)
        path_img = cv2.resize(path_img, None, fx=5, fy=5)
        cv2.imshow(f"_DEBUG_ Mode - PathFinding {self.ign}", path_img)
        cv2.waitKey(1)
