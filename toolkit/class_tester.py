import asyncio
import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations import RoyalsData
from royals.models_implementations.minimaps import KerningLine1Area1
from royals.models_implementations.characters import Magician
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
    char = Magician("FarmFest1", "large")
    mob = Bubbling()
    minimap = KerningLine1Area1()
    entire_map_area = minimap.get_entire_minimap_box(HANDLE)
    map_area = minimap.get_map_area_box(HANDLE)
    data.current_map = TestMap()
    data.current_minimap = minimap
    data.character = char
    data.update("current_minimap_area_box", "current_entire_minimap_box", "current_on_screen_position")

    generator = hit_closest_in_range(data, char.skills['Magic Claw'])
    while True:
        print(minimap.get_character_positions(HANDLE, map_area_box=map_area))
        # action = next(generator)
        # if callable(action):
        #     asyncio.run(action())
