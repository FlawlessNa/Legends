import multiprocessing.connection
import multiprocessing.managers
from abc import ABC
from botting.core import Bot
from botting.utilities import take_screenshot
from botting.visuals import InGameDetectionVisuals
from royals import royals_ign_finder, royals_job_finder
from royals.model.characters import MAPPING as CHARACTER_MAPPING
from royals.model.mechanics import MapleMap


class RoyalsBot(Bot, ABC):
    """
    A Bot subclass that defines the ign_finder callable and extends the init behavior.
    """

    ign_finder = royals_ign_finder

    def __init__(
        self,
        ign: str,
        metadata: multiprocessing.managers.DictProxy,
        game_map: str,
        detection_configs: str = None,
        client_size: str = "medium",
        models_path: dict[str, str] = None,
        character_class: str = None,
        open_minimap_editor: bool = False,
        **kwargs
    ) -> None:
        super().__init__(ign, metadata, **kwargs)
        self.handle = self.get_handle_from_ign(ign)
        class_name = character_class or royals_job_finder(self.handle)
        self.character_class = CHARACTER_MAPPING[class_name]
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.models_path = models_path
        self.game_map = game_map.replace("_", "").replace(" ", "")
        self.open_minimap_editor = open_minimap_editor
        self.kwargs = kwargs

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: multiprocessing.managers.BarrierProxy,  # type: ignore
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        Since virtually every bot will at some point require to know the character class
        and be made aware of the minimap position, those attributes are created here for
        convenience.
        """
        super().child_init(pipe, barrier)
        InGameDetectionVisuals.register_models(self.models_path)
        InGameDetectionVisuals.register_cache_id(self.data.handle)
        self.data.create_attribute(
            "character",
            lambda: self.character_class(
                self.ign, self.detection_configs, self.client_size
            ),
        )
        self.data.create_attribute(
            "current_map",
            lambda: MapleMap(self.game_map, self.open_minimap_editor, **self.kwargs)
        )
        self.data.create_attribute(
            "current_minimap", lambda: self.data.current_map.minimap
        )
        self.data.create_attribute(
            "current_grid", lambda: self.data.current_minimap.generate_grid(
                allow_teleport=self.data.character.skills.get("Teleport") is not None,
                speed_multiplier=(
                    self.data.speed_multiplier if self.data.has_ap_menu_attributes
                    else 1.00
                ),
                jump_multiplier=(
                    self.data.jump_multiplier if self.data.has_ap_menu_attributes
                    else 1.00
                )
            )
        )
        self.data.create_attribute("current_mobs", lambda: self.data.current_map.mobs)
        self.data.create_attribute(
            "current_client_img",
            lambda: take_screenshot(self.data.handle),
            threshold=0.1,
        )
