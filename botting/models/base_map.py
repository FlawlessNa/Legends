from abc import ABC

from .base_minimap import BaseMinimap
from .base_mob import BaseMob
from botting.utilities import Box
from botting.visuals import InGameBaseVisuals


class BaseMap(InGameBaseVisuals, ABC):
    """
    This class is an example of how a map can be defined.
    A map may contain the following:
    - A set of mobs that can be found within it.
    - A set of coordinates that define the on-screen area used for detection.
    - A Minimap associated with that Map
    - Connections to other minimaps
    This is merely an example. Map implementations may vary.
    """

    detection_box: Box

    def __init__(
        self,
        minimap: BaseMinimap,
        mobs: list[BaseMob] | None = None,
        connections: list["BaseMap"] | None = None,
    ) -> None:
        self.mobs = mobs
        self.minimap = minimap
        self.connections = connections