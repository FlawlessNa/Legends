import multiprocessing.connection
import multiprocessing.managers
import threading
from abc import ABC
from typing import Any

from botting.core import Bot
from botting.screen import frame_source
from botting.visuals import InGameDetectionVisuals
from maple.model.characters import MAPPING as CHARACTER_MAPPING
from maple.model.mechanics import MapleMap
from maple.screen.client import find_client


class MapleBot(Bot, ABC):
    """
    A Bot on the MapleStory client: it finds the client by its window class and
    executable, and takes its job from the profile's `character_class`.
    """

    def __init__(
        self,
        ign: str,
        metadata: multiprocessing.managers.DictProxy,
        game_map: str,
        detection_configs: str | None = None,
        client_size: str = "medium",
        models_path: dict[str, str] | None = None,
        character_class: str | None = None,
        open_minimap_editor: bool = False,
        **kwargs: Any,  # noqa: ANN401
    ) -> None:
        super().__init__(ign, metadata, **kwargs)
        if not character_class:
            raise ValueError(
                f"{type(self).__name__} for {ign!r} needs `character_class` in the "
                "profile's settings, one of: " + ", ".join(sorted(CHARACTER_MAPPING))
            )
        self.character_class = CHARACTER_MAPPING[character_class.title()]
        self.detection_configs = detection_configs
        self.client_size = client_size
        self.models_path = models_path
        self.game_map = game_map.replace("_", "").replace(" ", "")
        self.open_minimap_editor = open_minimap_editor
        self.kwargs = kwargs
        self.kwargs.update(ign=ign)

    def find_handle(self) -> int:
        return find_client()

    def child_init(
        self,
        pipe: multiprocessing.connection.Connection,
        barrier: threading.Barrier,
    ) -> None:
        """
        Called by the Engine to create Bot within Child process.
        Since virtually every bot will at some point require to know the character class
        and be made aware of the minimap position, those attributes are created here for
        convenience.
        """
        super().child_init(pipe, barrier)
        # `Bot.child_init` is what builds `self.data`; everything below reads it,
        # including the lambdas, which a narrowing assert alone would not reach.
        assert self.data is not None
        assert self.models_path is not None
        data = self.data
        InGameDetectionVisuals.register_models(self.models_path)
        InGameDetectionVisuals.register_cache_id(data.handle)
        data.create_attribute(
            "character",
            lambda: self.character_class(
                self.ign, self.detection_configs, self.client_size
            ),
        )
        data.create_attribute(
            "current_map",
            lambda: MapleMap(self.game_map, self.open_minimap_editor, **self.kwargs),
        )
        data.create_attribute("current_minimap", lambda: data.current_map.minimap)
        data.create_attribute(
            "current_grid",
            lambda: data.current_minimap.generate_grid(
                allow_teleport=data.character.skills.get("Teleport") is not None,
                speed_multiplier=(
                    data.speed_multiplier if data.has_ap_menu_attributes else 1.00
                ),
                jump_multiplier=(
                    data.jump_multiplier if data.has_ap_menu_attributes else 1.00
                ),
            ),
        )
        data.create_attribute("current_mobs", lambda: data.current_map.mobs)
        data.create_attribute(
            "current_client_img",
            lambda: frame_source().grab(data.handle).pixels,
            threshold=0.1,
        )
        data.set_static("speed_multiplier", self.kwargs.get("speed_multiplier", 1.00))
        data.set_static("jump_multiplier", self.kwargs.get("jump_multiplier", 1.00))
