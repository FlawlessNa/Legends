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
        # print(inv.get_current_mesos(HANDLE))
        print(inv.get_active_tab(HANDLE, img))
        print(inv.get_tab_count('Cash', 'Equip'))
        # print('Displayed:', inv.is_displayed(HANDLE, img))
        # print('Extended:', inv.is_extended(HANDLE, img))
        #
        # print('Space left:', inv.get_space_left(HANDLE, img))
