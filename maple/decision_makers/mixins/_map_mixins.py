from collections.abc import Callable, Mapping
from functools import cached_property
from typing import Any

from botting.core import BotData
from botting.screen import Reading
from maple.decision_makers.providers.minimap import MinimapProvider, PositionReader
from maple.screen.minimap import MINIMAP, MinimapView
from maple.screen.position import VirtualPosition


class MinimapAttributesMixin:
    """
    Legacy: what an unported DecisionMaker used to create the minimap's data
    with. `MinimapProvider` serves that data now; this only asks for it, and
    reads a position for a runner that reads its own (the movement
    playground's). Goes with the last mixin.
    """

    data: BotData
    emit: Callable[[str, Mapping[str, Any] | None], None]
    MINIMAP_POS_REFRESH_RATE = MinimapProvider.REFRESH
    ERROR_HANDLING_TIME_LIMIT = MinimapProvider.TIME_LIMIT
    screen_readers = (MINIMAP,)

    def _read_minimap(self) -> Reading[MinimapView]:
        return self.data.minimap_reader.read(self.data.current_frame)

    @cached_property
    def _position_reader(self) -> PositionReader:
        return PositionReader(
            self,
            self.emit,
            fusion=lambda: getattr(self.data, "position_fusion", None),
            minimap=lambda: self.data.minimap_reading,
            frame=lambda: self.data.current_frame,
        )

    def _get_position(self) -> Reading[VirtualPosition]:
        """
        The character's virtual position, read now by this DecisionMaker's own
        `PositionReader`: see it for what an unsure read does.

        :raises ValueError: The minimap gave no position, or the bot has no
            position fusion.
        """
        return self._position_reader()

    def _create_minimap_attributes(self) -> None:
        """Ask `BotData` to build `MinimapProvider`, unless it is built already."""
        self.data.build_provider(MinimapProvider)
