import asyncio
import time
import os
import cv2
import numpy as np

from botting.core import controller
from botting.utilities import take_screenshot, Box, CLIENT_VERTICAL_MARGIN_PX, CLIENT_HORIZONTAL_MARGIN_PX
from royals.models_implementations import RoyalsData
from paths import ROOT
from royals.models_implementations.minimaps import MysteriousPath3
from royals.models_implementations.mobs import SelkieJr, Slimy
from royals.models_implementations.characters import Cleric
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