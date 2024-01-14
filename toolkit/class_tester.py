import asyncio
import time
import random
import numpy as np
import win32gui

from botting.core import controller
from botting.utilities import client_handler
from royals import royals_ign_finder

from royals.interface import AbilityMenu


HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api

if __name__ == "__main__":
    menu = AbilityMenu()
    while True:
        menu_pos = menu._menu_icon_position(HANDLE)
        int_box = menu_pos + menu.stat_mapper["INT"]
        asyncio.run(controller.mouse_move(HANDLE, int_box.center, total_duration=0))
        asyncio.run(controller.click(HANDLE, nbr_times=2))
        breakpoint()
        # asyncio.run(controller.click(HANDLE, nbr_times=2))
