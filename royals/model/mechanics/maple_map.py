import cv2
import logging
import numpy as np

from botting import PARENT_LOG
from .game_file_extraction.map_parser import MapParser
from .game_file_extraction.map_physics import MinimapPhysics
from .map_creation.minimap_edits_controller import MinimapEditor
from .map_creation.minimap_edits_model import MinimapEditsManager
from .map_creation.minimap_grid import MinimapGrid, ConnectionTypes
from ..interface import Minimap

logger = logging.getLogger(f'{PARENT_LOG}.{__name__}')


class MapleMinimap(Minimap):
    """
    Draws the raw minimap from game files.
    If a minimap subclass exists for the current minimap, it loads in the specified
    modifications and modifies the raw minimap based on those.
    """

    def __init__(
        self,
        parser: MapParser,
        raw_canvas: np.ndarray,
        features_manager: MinimapEditsManager,
        physics: MinimapPhysics,
    ):
        self.map_name = parser.map_name
        self.parser = parser
        self.raw_minimap = self._preprocess_canvas(raw_canvas)
        self.features_manager = features_manager
        self.modified_minimap = self.features_manager.apply_grid_edits(
            self.raw_minimap, apply_weights=True
        )
        self.physics = physics

    def generate_grid(
        self,
        allow_teleport: bool,
        speed_multiplier: float,
        jump_multiplier: float,
        include_portals: bool = True
    ) -> MinimapGrid:
        logger.info(
            f"Generating grid for {self.map_name}, {allow_teleport=}, "
            f"{speed_multiplier=}, {jump_multiplier=}, {include_portals=}"
        )
        grid = MinimapGrid(self.modified_minimap, grid_id=self.map_name)
        if include_portals:
            self._add_portals(grid)
        return self.features_manager.apply_pathfinding_edits(grid)

    @staticmethod
    def _preprocess_canvas(canvas: np.ndarray) -> np.ndarray:
        """
        Converts the canvas into a binary (unweighted) image.
        """
        if len(canvas.shape) == 3 and canvas.shape[-1] == 3:
            return cv2.cvtColor(
                np.where(canvas > 0, 1, 0).astype(np.uint8), cv2.COLOR_BGR2GRAY
            )
        else:
            return np.where(canvas > 0, 1, 0).astype(np.uint8)

    _preprocess_img = _preprocess_canvas

    def _add_portals(self, grid: MinimapGrid) -> None:
        offset_x, offset_y = self.parser.mini_cx, self.parser.mini_cy
        for portal in self.parser.portals.res:
            source = self.parser.get_minimap_coords(portal['x'], portal['y'])
            if not grid.node(*source).walkable:
                breakpoint()
            if self.parser.map_id == portal['target_map']:
                target_portal = self.parser.portals.get_portal(portal['target_name'])
                target = self.parser.get_minimap_coords(
                    target_portal['x'], target_portal['y']
                )
                grid.node(*source).connect(
                    grid.node(*target), ConnectionTypes.IN_MAP_PORTAL
                )
            else:
                breakpoint()



class MapleMap:
    """
    Class to hold the map of the game and its associated info.
    """
    def __init__(
        self, map_name: str, open_minimap_editor: bool = False, **kwargs
    ) -> None:
        self.map_name = map_name
        self.parser = MapParser(map_name)
        orig_minimap_canvas = self.parser.get_raw_minimap_grid(True)
        self.edits = MinimapEditsManager.from_json(map_name) or MinimapEditsManager()
        if open_minimap_editor:
            # This will block until the editor's mainloop is closed
            editor = MinimapEditor(
                map_name,
                orig_minimap_canvas,
                self.edits,
                include_character_position=kwargs.get('include_character_position', True),
                scale=kwargs.get('scale', 5),
            )
            self.edits = editor.edits

        physics = MinimapPhysics(
            1 / self.parser.minimap_scale_x, 1 / self.parser.minimap_scale_y
        )
        self.minimap = MapleMinimap(
            self.parser, orig_minimap_canvas, self.edits, physics
        )
        # mob_ids = self.parser.get_mobs_ids()
        # self.mobs = tuple(BaseMob(mob_id) for mob_id in mob_ids)

