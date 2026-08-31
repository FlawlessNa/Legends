import cv2
import os
from botting.utilities import client_handler
from maple import maple_ign_finder
from maple.model.interface import Minimap
from paths import ROOT


class DummyMinimap(Minimap):
    def _preprocess_img(self, *args, **kwargs) -> None:
        pass

HANDLE = client_handler.get_client_handle("StarBase", maple_ign_finder)
MAP_NAME = "BuddhaMinimap"

if __name__ == '__main__':
    minimap = DummyMinimap()
    img = minimap.get_minimap_title_img(HANDLE)
    cv2.imshow('Minimap Title', img)
    cv2.imwrite(
        os.path.join(ROOT, 'maple/assets/detection_images', f'{MAP_NAME}.png'), img
    )