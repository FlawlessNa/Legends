import numpy as np

from dataclasses import dataclass, field

from botting.core import GameData
from botting.utilities import Box


@dataclass
class RoyalsData(GameData):
    minimap_is_displayed: bool = field(repr=False, init=False)
    minimap_state: str = field(repr=False, init=False)
    current_minimap_title_img: np.ndarray = field(repr=False, init=False)
    current_minimap_area_box: Box = field(repr=False, init=False)

    def update(self, *args, **kwargs) -> None:
        pass
