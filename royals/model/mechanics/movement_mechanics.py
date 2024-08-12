import cv2
import logging
import numpy as np
from dataclasses import dataclass, field
from functools import lru_cache
from pathfinding.finder.a_star import AStarFinder
from pathfinding.finder.dijkstra import DijkstraFinder

from botting import PARENT_LOG
from .minimap_mechanics import MinimapConnection, MinimapPathingMechanics, MinimapNode

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.NOTSET
DEBUG = False


@dataclass
class MovementsData:
    inputs: field(default_factory=list)
    delays: field(default_factory=list)
    keys_to_release: field(default_factory=list)

    def __post_init__(self):
        assert len(self.inputs) == len(
            self.delays
        ), "Inputs and delays must be the same length."


class Movements:
    _debug = DEBUG

    def __init__(self, minimap: MinimapPathingMechanics):
        self.minimap = minimap
        self.finder = AStarFinder() if not minimap.grid.portals else DijkstraFinder()

    def __hash__(self):
        """Hash the minimap class."""
        return hash(self.minimap.__class__)

    def __eq__(self, other):
        """Check if the minimap is the same class."""
        return (
            isinstance(other, Movements)
            and self.minimap.__class__ == other.minimap.__class__
        )

    def compute_path(
        self, start: tuple[int, int], end: tuple[int, int]
    ) -> list[MinimapNode]:
        path = self._compute_path(start, end)
        self._run_debug(start, end, path)
        return path

    @lru_cache
    def path_into_movements(self, path: tuple[MinimapNode]) -> list[tuple[str, int]]:
        print("computing path")

    # def movements_into_actions(self, movements: list[tuple[str, int]]) -> callable:
    #     pass
    #
    # def action_buffer(self, requested_duration: float = 1.0) -> callable:
    #     pass
    #
    # def _compound_input_structure(self, movements: list[tuple[str, int]]) -> callable:
    #     """TODO - Need to establish a compound input structure from movements."""

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
        cv2.imshow("_DEBUG_ Mode - PathFinding", path_img)
        cv2.waitKey(1)
