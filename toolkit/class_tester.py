import asyncio
import cv2
import time
import random
import numpy as np
import win32gui

from botting.core import controller
from botting.utilities import client_handler, take_screenshot
from royals import royals_ign_finder
from royals.models_implementations.mechanics import MinimapConnection

from royals.models_implementations.minimaps import PathOfTime1Minimap, LudibriumMinimap
from royals.maps import PathOfTime1
from royals.interface import AbilityMenu, CharacterStats, InventoryMenu
from royals.actions import write_in_chat, cast_skill, telecast, teleport_once
from royals.characters import Bishop, Assassin

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
import win32api

if __name__ == "__main__":
    # from pathfinding.finder.a_star import AStarFinder
    # now = time.perf_counter()
    # test_door = (73, 39)
    # start = (61, 39)
    # end = (50, 82)
    # entire_map = PathOfTime1()
    # minimap = entire_map.minimap
    # town = entire_map.nearest_town
    # minimap.generate_grid_template(True)
    # town.generate_grid_template(True)
    #
    # minimap.grid.node(*test_door).connect(town.grid.node(*town.door_spot), MinimapConnection.PORTAL)
    #
    # finder = AStarFinder()
    # path, runs = finder.find_path(start, end, world)
    asyncio.run(controller.move(HANDLE, "WrongDoor", "left", 0.11764705882352941))
    breakpoint()


    # bish = Bishop("WrongDoor", "Elephant Cape", "large")
    # assa = Assassin("UluLoot", "Elephant Cape", "large")
    # now = time.perf_counter()
    # hs_img = bish.skills["Holy Symbol"].icon
    # haste_img = assa.skills["Haste"].icon
    # hs_gray = cv2.cvtColor(hs_img, cv2.COLOR_BGR2GRAY)
    # haste_gray = cv2.cvtColor(haste_img, cv2.COLOR_BGR2GRAY)
    #
    # def _match_buff_icon(icon_name: str, client_img, buff_img):
    #     results = cv2.matchTemplate(client_img, buff_img, cv2.TM_CCOEFF_NORMED)
    #     min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(results)
    #     rect = max_loc + (buff_img.shape[1], buff_img.shape[0])
    #     rect_img = client_img[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]]
    #     gray = cv2.cvtColor(rect_img, cv2.COLOR_BGR2GRAY)
    #     _, thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)
    #     bright_pixels = cv2.countNonZero(thresh)
    #     cv2.imshow(f"{icon_name}", cv2.resize(rect_img, None, fx=10, fy=10))
    #     cv2.waitKey(1)
    #     print(f"{icon_name} - {max_val} - {bright_pixels}")
    #
    # while True:
    #     client_img = take_screenshot(HANDLE)
    #     gray = cv2.cvtColor(client_img, cv2.COLOR_BGR2GRAY)
    #     _match_buff_icon("HS", client_img, hs_img)
    #     _match_buff_icon("Haste", client_img, haste_img)
    #
    #     breakpoint()

    print("total duration", time.perf_counter() - now)
