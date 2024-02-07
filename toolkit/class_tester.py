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


def calc_centroid(pts):
    n = len(pts)
    x = sum(pt[0] for pt in pts) / n
    y = sum(pt[1] for pt in pts) / n
    return int(x), int(y)


if __name__ == "__main__":
    minimap = LudibriumMinimap()
    character = Bishop("WrongDoor", "Elephant Cape", "large")
    map_area_box = minimap.get_map_area_box(HANDLE)

    while True:
        client_img = take_screenshot(HANDLE)
        minimap_img = map_area_box.extract_client_img(client_img)
        npcs = minimap.get_character_positions(HANDLE, 'NPC', client_img, map_area_box=map_area_box)
        cv2.circle(minimap_img, calc_centroid(npcs), 4, (0, 0, 255), -1)
        for npc in npcs:
            cv2.circle(minimap_img, npc, 4, (0, 255, 0), -1)
        cv2.imshow("minimap", cv2.resize(minimap_img, None, fx=4, fy=4))
        cv2.waitKey(1)
        print(npcs)

        # current = minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop()
        # time.sleep(0.5)
        # current_with_break = minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop()
        # actions = get_to_target(
        #     minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop(),
        #     (0, 0),
        #     minimap,
        # )
        # # breakpoint()
        # if actions:
        #     first_action = actions[0]
        #     args = (
        #         HANDLE,
        #         "WrongDoor",
        #         first_action.keywords["direction"],
        #     )
        #     kwargs = first_action.keywords.copy()
        #     kwargs.pop("direction", None)
        #     if first_action.func.__name__ == "teleport_once":
        #         kwargs.update(teleport_skill=character.skills["Teleport"])
        #     asyncio.run(partial(first_action.func, *args, **kwargs)())
