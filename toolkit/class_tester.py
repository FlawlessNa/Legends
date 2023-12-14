import asyncio
import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations import RoyalsData
from royals.models_implementations.minimaps import KerningLine1Area1
from royals.models_implementations.characters import Character
from royals.models_implementations.mobs import Bubbling
from royals.bot_implementations.actions.hit_mobs import hit_closest_in_range

HANDLE = 0x02300A26

class TestMap(BaseMap):
    def __init__(self):
        super().__init__(KerningLine1Area1(), [Bubbling()], None)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


if __name__ == "__main__":
    data = RoyalsData(HANDLE, 'FarmFest1')
    char = Character("FarmFest1", "large")
    mob = Bubbling()
    minimap = KerningLine1Area1()
    map_area = minimap.get_entire_minimap_box(HANDLE)
    data.current_map = TestMap()
    data.current_minimap = minimap
    data.character = char
    data.update("current_minimap_area_box", "current_entire_minimap_box", "current_on_screen_position")

    generator = hit_closest_in_range(data, 'c')
    while True:
        action = next(generator)
        if callable(action):
            asyncio.run(action())
