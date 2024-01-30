import asyncio
import cv2
import time
import random
import numpy as np
import win32gui

from botting.core import controller
from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder

from royals.models_implementations.minimaps import PathOfTime1Minimap
from royals.interface import AbilityMenu, CharacterStats, InventoryMenu


HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api
from botting.core.controls.controller_v2 import move
if __name__ == "__main__":
    now = time.perf_counter()
    asyncio.run(move(HANDLE,
                     "WrongDoor",
                     "left",
                     5,
                     )
                )
    print('total duration', time.perf_counter() - now)

    # inv = InventoryMenu()
    # minimap = PathOfTime1Minimap()
    # while True:
    #     inv.is_extended(HANDLE)
        # print(inv.read_item_name(HANDLE, controller.get_mouse_pos(HANDLE)))
        # img = take_screenshot(HANDLE)
        # cv2.imshow('client_img', img)
        # # extend_button = inv.get_abs_box(HANDLE, inv.extend_button)
        # boxes = inv.get_all_slots_boxes(HANDLE, img)
        #
        # for box in boxes:
        #     target = box.random()
        #     asyncio.run(controller.mouse_move(HANDLE, target, total_duration=0.1))


        # asyncio.run(controller.mouse_move(HANDLE, extend_button.random()))
        # breakpoint()
        #
        # print('Space left:', inv.get_space_left(HANDLE, img))
