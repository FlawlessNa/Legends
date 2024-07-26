import time

from botting.utilities import client_handler
from royals import royals_ign_finder

from royals.models_implementations.minimaps import (
    PathOfTime1Minimap,
    MuddyBanks2Minimap,
    TrendZoneMetropolisMinimap,
    FantasyThemePark1Minimap,
    KampungVillageMinimap,
    LudibriumMinimap,
)
# from royals.maps import PathOfTime1
from royals.interface import AbilityMenu, CharacterStats, InventoryMenu
from royals.actions import write_in_chat, cast_skill, telecast, teleport
from royals.characters import Bishop, Assassin
from royals.models_implementations.mechanics.path_into_movements import get_to_target

import win32api
from royals.models_implementations.mechanics.inventory import InventoryActions
import royals.actions as act
from botting.utilities import Box, find_image
import os
from paths import ROOT

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)


if __name__ == "__main__":
    bishop = Bishop("WrongDoor", "Elephant Cape", "large")
    minimap = KampungVillageMinimap()
    minimap.generate_grid_template(allow_teleport=True)
    # target = minimap.door_spot[0]
    import random
    area_box = minimap.get_map_area_box(HANDLE)
    while True:
        # print(area_box.width, area_box.height)
        # print('Area Box', area_box.width, area_box.height)
        npc_pos = minimap.get_character_positions(HANDLE, map_area_box=area_box)
        get_to_target(
            npc_pos[0],
            minimap.door_spot,
            minimap,
            HANDLE,
            'alt',
            teleport_skill=bishop.skills['Teleport'],
            ign='WrongDoor'
        )
        print('Char Pos', npc_pos)
    #
    # start = time.time()
    # initial_list = ludi.get_character_positions(
    #     HANDLE,
    #     "NPC",
    # )
    # while True:
    #     new_list = ludi.get_character_positions(
    #         HANDLE,
    #         "NPC",
    #     )
    #     if len(new_list) == len(initial_list):
    #         vert_distances = [
    #             new_list[i][1] - initial_list[i][1]
    #             for i in range(len(new_list))
    #         ]
    #         if all(v == 0 for v in vert_distances):
    #             horiz_dist = sum(
    #                 (new_list[i][0] - initial_list[i][0])
    #                 for i in range(len(new_list))
    #             ) / len(new_list)
    #             print(time.time(), 'Horizonal distance:', horiz_dist)
    #
    # print(time.time() - start)
