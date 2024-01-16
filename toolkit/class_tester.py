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
    menu = AbilityMenu()
    stats = CharacterStats()
    inv = InventoryMenu()
    while True:
        img = take_screenshot(HANDLE)
        cv2.imshow('mesos', img)
        cv2.waitKey(1)
        print('Extended:', inv.is_extended(HANDLE, img))
        extend_button = inv.get_abs_box(HANDLE, inv.extend_button)
        cv2.imshow('test', take_screenshot(HANDLE, extend_button))
        cv2.waitKey(1)
        asyncio.run(controller.mouse_move(HANDLE, extend_button.random()))
        breakpoint()
        #
        # print('Space left:', inv.get_space_left(HANDLE, img))
