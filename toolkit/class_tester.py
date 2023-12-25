import os
import cv2
import numpy as np

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
    test = Cleric("FarmFest1", 'Elephant Cape', "large")
    minimap = MysteriousPath3()
    slimy = Slimy()
    selkie = SelkieJr()
    entire_box = minimap.get_entire_minimap_box(HANDLE)
    hide_tv_smega_box = Box(left=700, right=1024, top=0, bottom=300)
    hide_minimap_box = Box(
        max(
            0,
            entire_box.left - CLIENT_HORIZONTAL_MARGIN_PX - 5,
        ),
        entire_box.right + CLIENT_HORIZONTAL_MARGIN_PX + 5,
        max(
            0,
            entire_box.top - CLIENT_VERTICAL_MARGIN_PX - 10,
        ),
        entire_box.bottom + CLIENT_VERTICAL_MARGIN_PX + 5,
    )
    while True:
        img = take_screenshot(HANDLE)
        slimy_rects = slimy.get_onscreen_mobs(img)
        selkie_rects = selkie.get_onscreen_mobs(img)
        for (x, y, w, h) in slimy_rects:
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 2)
        for (x, y, w, h) in selkie_rects:
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imshow('img', img)
        cv2.waitKey(1)
        # print(
        #     test.get_onscreen_position(
        #         None, HANDLE, regions_to_hide=[hide_minimap_box, hide_tv_smega_box]
        #     )
        # )
        # print(minimap.get_character_positions(HANDLE))
        # print(minimap.get_map_area_box(HANDLE))
        # img = take_screenshot(HANDLE)
        # processed = cv2.inRange(img, (68, 68, 51), (68, 68, 51))
        # contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # # for cnt in contours:
        # #     x, y, w, h = cv2.boundingRect(cnt)
        # #     cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        # rects = [cv2.boundingRect(cnt) for cnt in contours if 10 <= cv2.contourArea(cnt) <= 90]
        # areas = [cv2.contourArea(cnt) for cnt in contours if 10 <= cv2.contourArea(cnt) <= 90]
        # grouped = cv2.groupRectangles(rects, 1, 2)
        # for x, y, w, h in grouped[0]:
        # # for x, y, w, h in rects:
        #     cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        # cv2.imshow('img', img)
        # cv2.waitKey(1)
        # print(np.count_nonzero(processed))
