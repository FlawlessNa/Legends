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
    # for _ in range(10):
    #     asyncio.run(controller.press(HANDLE, 'a', delay=0))
    #     time.sleep(1.075)
    # asyncio.run(cast_skill(HANDLE, "WrongDoor", bishop.skills['Genesis']))
    # asyncio.run(test())
    # from botting.core.controls.inputs.focused_inputs import activate, FOCUS_LOCK
    #
    # asyncio.run(activate(HANDLE))
    # FOCUS_LOCK.release()
    # asyncio.run(activate(0x01460776))
    # FOCUS_LOCK.release()
    # asyncio.run(activate(HANDLE))
    # FOCUS_LOCK.release()
    for _ in range(2):
        # asyncio.run(act.move(HANDLE, "left", 1, ))
        # asyncio.run(act.move(HANDLE, "right", 1, secondary_direction="up"))
        asyncio.run(act.jump_on_rope(HANDLE, "right", "alt"))
        # asyncio.run(act.single_jump(HANDLE, "right", 'alt',))
        # asyncio.run(act.single_jump(HANDLE, "left", 'alt', ))
        # asyncio.run(
        #     act.teleport(
        #         HANDLE,
        #         "WrongDoor",
        #         "right",
        #         bishop.skills["Teleport"],
        #         3,
        #     )
        # )
        # asyncio.run(
        #     act.teleport(
        #         HANDLE,
        #         "WrongDoor",
        #         "left",
        #         bishop.skills["Teleport"],
        #         3
        #     )
        # )
    # asyncio.run(act.teleport(HANDLE, "WrongDoor", "left", bishop.skills['Teleport'], 3))
    # asyncio.run(act.move(0x01460776, "up", 1))
    print(time.time() - start)
