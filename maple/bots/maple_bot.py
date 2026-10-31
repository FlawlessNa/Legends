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
from maple.model.mechanics.minimap_creation.minimap_edits_model import (
    MinimapEditsManager,
)
from maple.screen.client import find_client
from maple.screen.locator import FrameCheck
from maple.screen.minimap import NW, MinimapReader
from maple.screen.sprites import Profile, enabled_readers, load_reader_sprites
from maple.screen.status_bar import BACKGROUND as STATUS_BAR_BACKGROUND
from maple.screen.status_bar import StatusBarReader


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
        self.job = character_class.title()
        self.character_class = CHARACTER_MAPPING[self.job]
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
        # The readers' sprites are loaded once, before any reader attribute
        # exists: a missing or stale store refuses the start here, not mid-cycle.
        map_file = MinimapEditsManager.from_json(self.game_map)
        reader_sprites = load_reader_sprites(
            enabled_readers(self._decision_makers()),
            Profile(
                job=self.job,
                game_map=self.game_map,
                map_id=map_file.map_id if map_file is not None else None,
            ),
        )
        data.set_static("reader_sprites", reader_sprites)
        if reader_sprites.build is not None:
            frame_check = FrameCheck(reader_sprites)
            data.set_static("frame_check", frame_check)
            if STATUS_BAR_BACKGROUND in reader_sprites.canvases:
                data.set_static(
                    "status_bar_reader", StatusBarReader(reader_sprites, frame_check)
                )
            if NW in reader_sprites.canvases:
                data.set_static(
                    "minimap_reader", MinimapReader(reader_sprites, frame_check)
                )
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
        # One capture serves both: the readers take the `Frame`, the older
        # pixel consumers its pixels. Refreshing the pixels captures a new frame,
        # as it did before, so `update_attribute("current_client_img")` still
        # means a fresh capture.
        data.create_attribute(
            "current_frame", lambda: frame_source().grab(data.handle), threshold=0.1
        )

        def client_img() -> Any:  # noqa: ANN401 - the frame's pixels, as before
            data.update_attribute("current_frame")
            return data.current_frame.pixels

        data.create_attribute("current_client_img", client_img, threshold=0.1)
        data.set_static("speed_multiplier", self.kwargs.get("speed_multiplier", 1.00))
        data.set_static("jump_multiplier", self.kwargs.get("jump_multiplier", 1.00))
