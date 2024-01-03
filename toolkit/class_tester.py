import asyncio
import time
import numpy as np

from botting.core import controller
from royals.interface.dynamic_components.minimap import Minimap



class FakeMinimap(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


HANDLE = 0x00F90FA4


if __name__ == "__main__":
    # asyncio.run(controller.press(HANDLE, 'up', down_or_up='keydown', silenced=False))
    for _ in range(15):
        asyncio.run(controller.press(HANDLE, 'insert', silenced=True, enforce_delay=False, cooldown=0, delay=0))
        time.sleep(2.2)