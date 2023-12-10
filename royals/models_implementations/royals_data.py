import numpy as np

from dataclasses import dataclass, field

from botting.core import GameData
from botting.utilities import Box
from royals.models_implementations.mechanics import MinimapPathingMechanics


@dataclass
class RoyalsData(GameData):
    minimap_is_displayed: bool = field(repr=False, init=False)
    minimap_state: str = field(repr=False, init=False)
    current_direction: str = field(default='right', repr=False, init=False)
    current_minimap: MinimapPathingMechanics = field(repr=False, init=False)
    current_minimap_title_img: np.ndarray = field(repr=False, init=False)
    current_minimap_area_box: Box = field(repr=False, init=False)
    current_minimap_position: tuple[int, int] = field(repr=False, init=False)

    def update(self, *args) -> None:
        if 'current_minimap_position' in args:
            new_pos = self.current_minimap.get_character_positions(self.handle, map_area_box=self.current_minimap_area_box)
            assert len(new_pos) == 1
            self.current_minimap_position = new_pos.pop()
