import cv2
import numpy as np

from .game_file_extraction.map_parser import MapParser
from .map_creation.minimap_edits_controller import MinimapEditor
from .map_creation.minimap_edits_model import MinimapEditsManager
from .map_creation.minimap_grid import MinimapGrid


class MapleMinimap:
    """
    Draws the raw minimap from game files.
    If a minimap subclass exists for the current minimap, it loads in the specified
    modifications and modifies the raw minimap based on those.
    """
    def __init__(
        self,
        raw_canvas: np.ndarray,
        features_manager: MinimapEditsManager
    ):
        self.raw_minimap = self._preprocess_canvas(raw_canvas)
        self.features_manager = features_manager
        self.modified_minimap = self.features_manager.apply_minimap_edits(
            self.raw_minimap
        )
        # self.raw_grid = MinimapGrid(canvas=self.modified_minimap)
        # self.modified_grid = self.features_manager.apply_grid_edits(self.raw_grid)

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


class MapleMap:
    """
    Class to hold the map of the game and its associated info.
    """
    def __init__(
        self, map_name: str, open_minimap_editor: bool = False, **kwargs
    ) -> None:
        self.map_name = map_name
        self.parser = MapParser(map_name)
        # self.vr_canvas = self.parser.get_vr_canvas()
        orig_minimap_canvas = self.parser.get_raw_minimap_grid(True)
        self.edits = MinimapEditsManager.from_json(map_name)
        if open_minimap_editor:
            # This will block until the editor's mainloop is closed
            editor = MinimapEditor(map_name, orig_minimap_canvas, self.edits, **kwargs)
            self.edits = editor.edits

        self.minimap = MapleMinimap(orig_minimap_canvas, self.edits)

        # mob_ids = self.parser.get_mobs_ids()
        # self.mobs = tuple(BaseMob(mob_id) for mob_id in mob_ids)

