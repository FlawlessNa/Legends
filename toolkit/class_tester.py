import asyncio
import cv2
import time
import random
import numpy as np
import win32gui
from functools import partial

from botting.core import controller
from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder
from royals.models_implementations.mechanics import MinimapConnection

from royals.models_implementations.minimaps import PathOfTime1Minimap, LudibriumMinimap
from royals.maps import PathOfTime1
from royals.interface import AbilityMenu, CharacterStats, InventoryMenu
from royals.actions import write_in_chat, cast_skill, telecast, teleport_once
from royals.characters import Bishop, Assassin
from royals.models_implementations.mechanics.path_into_movements import get_to_target

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api
from royals.models_implementations.mechanics.inventory import InventoryActions

def calc_centroid(pts):
    n = len(pts)
    x = sum(pt[0] for pt in pts) / n
    y = sum(pt[1] for pt in pts) / n
    return int(x), int(y)


if __name__ == "__main__":
    asyncio.run(controller.click(HANDLE, "down"))
    time.sleep(0.05)
    asyncio.run(controller.click(HANDLE, "up"))
    # asyncio.run(controller.press(HANDLE, 'left', down_or_up='keydown'))
    # asyncio.run(controller.press(HANDLE, 'a', down_or_up='keydown'))
