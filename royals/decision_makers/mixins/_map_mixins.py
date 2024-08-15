import logging

from botting import PARENT_LOG
from botting.core import BotData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class MinimapAttributesMixin:
    data: BotData
    MINIMAP_POS_REFRESH_RATE = 0.1

    def _get_minimap_pos(self) -> tuple[int, int]:
        return self.data.current_minimap.get_character_positions(
            self.data.handle, map_area_box=self.data.current_minimap_area_box
        ).pop()

    def _create_minimap_attributes(self) -> None:
        self.data.create_attribute(
            "current_minimap_area_box",
            lambda: self.data.current_minimap.get_map_area_box(self.data.handle),
        )
        self.data.create_attribute(
            "current_minimap_position",
            self._get_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
        )
        self.data.create_attribute(
            "current_entire_minimap_box",
            lambda: self.data.current_minimap.get_entire_minimap_box(self.data.handle),
        )
