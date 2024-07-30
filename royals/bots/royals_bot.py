import multiprocessing.connection
import multiprocessing.managers
from abc import ABC
from botting.core.botv2.bot import Bot
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
        **kwargs
    ) -> None:
        super().__init__(ign, metadata, **kwargs)
        self.handle = self.get_handle_from_ign(ign)
        self.character_class = CHARACTER_MAPPING[royals_job_finder(self.handle)]
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.game_map = game_map

    def child_init(self, pipe: multiprocessing.connection.Connection) -> None:
        """
        Called by the Engine to create Bot within Child process.
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
