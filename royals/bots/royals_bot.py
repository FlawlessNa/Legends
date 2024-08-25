import multiprocessing.connection
import multiprocessing.managers
from abc import ABC
from botting.core import Bot
from botting.utilities import take_screenshot
from royals import royals_ign_finder, royals_job_finder
from royals.model.characters import MAPPING as CHARACTER_MAPPING
from royals.model.maps import RoyalsMap


class RoyalsBot(Bot, ABC):
    """
    A Bot subclass that defines the ign_finder callable and extends the init behavior.
    """

    ign_finder = royals_ign_finder

    def __init__(
        self,
        ign: str,
        metadata: multiprocessing.managers.DictProxy,
        detection_configs: str,
        client_size: str,
        game_map: type[RoyalsMap],
        character_class: str = None,
        **kwargs
    ) -> None:
        super().__init__(ign, metadata, **kwargs)
        self.handle = self.get_handle_from_ign(ign)
        class_name = character_class or royals_job_finder(self.data.handle)
        self.character_class = CHARACTER_MAPPING[class_name]
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.game_map = game_map

    def child_init(self, pipe: multiprocessing.connection.Connection) -> None:
        """
        Called by the Engine to create Bot within Child process.
        Since virtually every bot will at some point require to know the character class
        and be made aware of the minimap position, those attributes are created here for
        convenience.
        """
        super().child_init(pipe)
        self.data.create_attribute(
            "character",
            lambda: self.character_class(
                self.ign, self.detection_configs, self.client_size
            ),
        )
        self.data.create_attribute("current_map", lambda: self.game_map())
        self.data.create_attribute(
            "current_minimap", lambda: self.data.current_map.minimap
        )
        self.data.create_attribute("current_mobs", lambda: self.data.current_map.mobs)
        self.data.create_attribute(
            "current_client_img",
            lambda: take_screenshot(self.data.handle),
            threshold=0.1,
        )
