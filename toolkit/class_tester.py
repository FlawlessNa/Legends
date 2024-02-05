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

if __name__ == "__main__":
    minimap = PathOfTime1Minimap()
    character = Bishop("WrongDoor", "Elephant Cape", "large")
    map_area_box = minimap.get_map_area_box(HANDLE)
    # initial_position = minimap.get_character_positions(
    #     HANDLE, map_area_box=map_area_box
    # ).pop()
    initial_position = (54, 54)
    minimap.generate_grid_template(False)
    minimap.grid.node(*initial_position).connect(
        minimap.grid.node(0, 0), MinimapConnection.PORTAL
    )
    while minimap.is_displayed(HANDLE):
        current = minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop()
        time.sleep(0.5)
        current_with_break = minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop()
        actions = get_to_target(
            minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop(),
            (0, 0),
            minimap,
        )
        # breakpoint()
        if actions:
            first_action = actions[0]
            args = (
                HANDLE,
                "WrongDoor",
                first_action.keywords["direction"],
            )
            kwargs = first_action.keywords.copy()
            kwargs.pop("direction", None)
            if first_action.func.__name__ == "teleport_once":
                kwargs.update(teleport_skill=character.skills["Teleport"])
            asyncio.run(partial(first_action.func, *args, **kwargs)())
