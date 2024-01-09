import asyncio
import time
import random
import numpy as np

from botting.core import controller
from royals.actions import telecast
from royals.interface.dynamic_components.minimap import Minimap
from royals.models_implementations.minimaps import KerningLine1Area1Minimap
from royals.characters import Bishop



class FakeMinimap(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


HANDLE = 0x00071BE4


if __name__ == "__main__":
    char = Bishop('FarmFest1', 'Elephant Cape', 'large')
    # asyncio.run(controller.press(HANDLE, 'up', down_or_up='keydown', silenced=False))
    minimap = KerningLine1Area1Minimap()
    while True:        # box = minimap.get_map_area_box(HANDLE)
        print(minimap.get_character_positions(HANDLE))
        # print(minimap.get_character_positions(HANDLE))
    # for _ in range(5):
    #     asyncio.run(telecast(HANDLE, 'FarmFest1', random.choice(['left', 'right']), char.skills['Teleport'], char.skills['Genesis']))

