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
from royals.actions import write_in_chat, cast_skill, telecast, teleport
from royals.characters import Bishop, Assassin
from royals.models_implementations.mechanics.path_into_movements import get_to_target

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api
from royals.models_implementations.mechanics.inventory import InventoryActions
import royals.actions as act
from botting.utilities import Box, find_image
import os
from paths import ROOT

def calc_centroid(pts):
    n = len(pts)
    x = sum(pt[0] for pt in pts) / n
    y = sum(pt[1] for pt in pts) / n
    return int(x), int(y)


async def test():
    async with asyncio.TaskGroup() as tg:
        t2 = tg.create_task(controller.move(HANDLE, "WrongDoor", "left", 5))
        await asyncio.sleep(1)
        # tg.create_task(controller.press(HANDLE, 'v', silenced=True))
        t1 = tg.create_task(cast_skill(HANDLE, "WrongDoor", bishop.skills["Genesis"]))
        # t1.cancel()


if __name__ == "__main__":
    bishop = Bishop("WrongDoor", "Elephant Cape", "large")
    start = time.time()
    asyncio.run(act.write_in_chat(HANDLE, "Hello", silenced=False, channel='party'))
    # for _ in range(10):
    #     asyncio.run(controller.press(HANDLE, 'a', delay=0))
    #     time.sleep(1.075)
    # asyncio.run(cast_skill(HANDLE, "WrongDoor", bishop.skills['Genesis']))
    # asyncio.run(test())
    # from botting.core.controller.inputs.focused_inputs import activate, FOCUS_LOCK
    #
    # asyncio.run(activate(HANDLE))
    # FOCUS_LOCK.release()
    # asyncio.run(activate(0x01460776))
    # FOCUS_LOCK.release()
    # asyncio.run(activate(HANDLE))
    # FOCUS_LOCK.release()
    # asyncio.run(telecast(HANDLE, "WrongDoor", "left", bishop.skills["Teleport"], bishop.skills["Genesis"], 0))
    # sell_button_offset: Box = Box(left=268, right=227, top=34, bottom=-30, offset=True)
    # first_shop_slot_offset: Box = Box(
    #     left=135, right=160, top=124, bottom=80, offset=True
    # )
    # shop_img_needle = cv2.imread(
    #     os.path.join(ROOT, "royals/assets/detection_images/Open NPC Shop.png")
    # )
    # current_client_img = take_screenshot(HANDLE)
    # match = find_image(current_client_img, shop_img_needle)
    # box = first_shop_slot_offset + match[0]
    # num_clicks = 10
    # button = sell_button_offset + match[0]
    #
    # asyncio.run(
    #     InventoryActions._clear_inventory(
    #         HANDLE,
    #         box.random(), button.random(), num_clicks
    #     )
    # )
    print(time.time() - start)
