from botting.utilities import client_handler
from royals import royals_ign_finder

from royals.model.minimaps import (
    KampungVillageMinimap,
)

# from royals.maps import PathOfTime1
from royals.model.characters import Bishop
from royals.model.mechanics.path_into_movements import get_to_target

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)


if __name__ == "__main__":
    bishop = Bishop("WrongDoor", "Elephant Cape", "large")
    minimap = KampungVillageMinimap()
    minimap.generate_grid_template(allow_teleport=True)
    # target = minimap.door_spot[0]
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
            "alt",
            teleport_skill=bishop.skills["Teleport"],
            ign="WrongDoor",
        )
        print("Char Pos", npc_pos)
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
