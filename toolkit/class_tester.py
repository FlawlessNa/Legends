import asyncio
import time
import numpy as np

from botting.core import controller
from royals.interface.dynamic_components.minimap import Minimap
from royals.models_implementations.minimaps import BuddhaMinimap



class FakeMinimap(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


HANDLE = 0x00F90FA4


if __name__ == "__main__":
    # asyncio.run(controller.press(HANDLE, 'up', down_or_up='keydown', silenced=False))
    minimap = BuddhaMinimap()
    while True:
        # box = minimap.get_map_area_box(HANDLE)
        print(minimap.get_character_positions(HANDLE))
        # print(minimap.get_character_positions(HANDLE))
