from .map_creation.map_game_file_extractor import MapParser
from .map_creation.minimap_editor import MinimapEditor
from .map_creation.minimap_edits import MinimapEditsManager


class RoyalsMinimap:
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
        self.raw_minimap = raw_canvas
        self.features_manager = features_manager
        self.modified_minimap = self.features_manager.apply_edits(self.raw_minimap)


class RoyalsMap:
    """
    Class to hold the map of the game and its associated info.
    """
    def __init__(
        self, map_name: str, open_minimap_editor: bool = False, **kwargs
    ) -> None:
        self.map_name = map_name
        self.parser = MapParser(map_name)
        self.vr_canvas = self.parser.get_vr_canvas()
        orig_minimap_canvas = self.parser.get_minimap_canvas()
        self.edits = MinimapEditsManager.from_json(map_name)
        if open_minimap_editor:
            # This will block until the editor's mainloop is closed
            editor = MinimapEditor(orig_minimap_canvas, self.edits, **kwargs)
            self.edits = editor.edits

        self.minimap = RoyalsMinimap(orig_minimap_canvas, self.edits)

        mob_ids = self.parser.get_mobs_ids()
        self.mobs = tuple(BaseMob(mob_id) for mob_id in mob_ids)

