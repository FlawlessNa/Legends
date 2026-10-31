import os

import cv2

from maple.model.interface import Minimap
from maple.screen.client import find_client
from paths import ROOT


class DummyMinimap(Minimap):
    def _preprocess_img(self, *args: object, **kwargs: object) -> None:
        pass


HANDLE = find_client()
MAP_NAME = "BuddhaMinimap"

if __name__ == "__main__":
    minimap = DummyMinimap()
    img = minimap.get_minimap_title_img(HANDLE)
    cv2.imshow("Minimap Title", img)
    cv2.imwrite(
        os.path.join(ROOT, "maple/assets/detection_images", f"{MAP_NAME}.png"), img
    )
