from abc import ABC
from dataclasses import dataclass, field

from botting.models_abstractions import BaseMap, BaseMob
from botting.utilities import Box
from royals.model.mechanics import MinimapPathingMechanics


@dataclass
class RoyalsMap(BaseMap, ABC):
    """
    Base Map class for Royals, where the minimap is a MinimapPathingMechanics instance.
    """

    detection_box: Box
    mobs: tuple[BaseMob]
    minimap: MinimapPathingMechanics
    path_to_shop: "RoyalsMap" = field(default=None)
