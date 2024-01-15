import asyncio
import cv2
import time
import random
import numpy as np
import win32gui

from botting.core import controller
from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder

from royals.interface import AbilityMenu, CharacterStats


HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api

if __name__ == "__main__":
    menu = AbilityMenu()
    stats = CharacterStats()
    while True:
        img = take_screenshot(HANDLE, stats.level_box)
        cv2.imshow("test", img)
        cv2.waitKey(1)
        print(stats.get_level(HANDLE))
