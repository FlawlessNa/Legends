import asyncio
import os
import cv2
import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations import RoyalsData
from royals.models_implementations.minimaps import (
    KerningLine1Area1,
    LudiFreeMarketTemplate,
)
from paths import ROOT
from botting.utilities import take_screenshot
from royals.models_implementations.characters import Magician
from royals.models_implementations.maps import SubwayLine1Area1
from royals.models_implementations.mobs import Bubbling
from royals.bot_implementations.actions.hit_mobs import hit_closest_in_range
from royals.bot_implementations.actions.random_rotation import random_rotation


HANDLE = 0x02300A26


if __name__ == "__main__":
    data = RoyalsData(HANDLE, "FarmFest1")
    data.character = Magician("FarmFest1", "large")
    data.current_map = SubwayLine1Area1()
    data.current_minimap = data.current_map.minimap
    data.current_minimap_area_box = data.current_minimap.get_map_area_box(HANDLE)
    data.update("current_minimap_position")
    # generator = random_rotation(data)

    model = cv2.CascadeClassifier(os.path.join(ROOT,
        "royals/assets/detection_models/w40-h40-numPos500-numNeg2000-numStages9-maxFA0.3-minHR0.999.xml")
    )  # THIS ONE IS ACTUALLY VERY GOOD!
    while True:
        print(data.current_minimap.get_character_positions(HANDLE))
        box = data.current_minimap.get_map_area_box(HANDLE)
        print('width', box.width)
        print('height', box.height)
        breakpoint()

        # img = take_screenshot(HANDLE, data.character.detection_box_large_client)
        # rects, lvls, weights = model.detectMultiScale3(
        #     img, 1.1, 6, 0, (50, 50), (90, 90), True
        # )
        # if len(weights):
        #     max_conf = np.argmax(weights)
        #     (x, y, w, h) = rects[max_conf]
        #     cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)

        # on_screen_pos = data.character.get_onscreen_position(img, handle=HANDLE)
