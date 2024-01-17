import asyncio
import cv2
import time
import random
import numpy as np
import win32gui

from botting.core import controller
from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder

from royals.interface import AbilityMenu, CharacterStats, InventoryMenu


HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api

if __name__ == "__main__":

    inv = InventoryMenu()
    while True:
        img = take_screenshot(HANDLE)
        cv2.imshow('client_img', img)
        # extend_button = inv.get_abs_box(HANDLE, inv.extend_button)
        boxes = inv.get_all_slots_boxes(HANDLE, img)

        for box in boxes:
            target = box.random()
            asyncio.run(controller.mouse_move(HANDLE, target, total_duration=0.1))


        # asyncio.run(controller.mouse_move(HANDLE, extend_button.random()))
        # breakpoint()
        #
        # print('Space left:', inv.get_space_left(HANDLE, img))
