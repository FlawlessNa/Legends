import time

from botting.utilities import client_handler
from royals import royals_ign_finder

from royals.models_implementations.minimaps import LudibriumMinimap
from royals.characters import Bishop

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)


if __name__ == "__main__":
    bishop = Bishop("WrongDoor", "Elephant Cape", "large")
    ludi = LudibriumMinimap()
    area_box = ludi.get_map_area_box(HANDLE)

    start = time.time()
    initial_list = ludi.get_character_positions(
        HANDLE,
        "NPC",
    )
    while True:
        new_list = ludi.get_character_positions(
            HANDLE,
            "NPC",
        )
        if len(new_list) == len(initial_list):
            vert_distances = [
                new_list[i][1] - initial_list[i][1]
                for i in range(len(new_list))
            ]
            if all(v == 0 for v in vert_distances):
                horiz_dist = sum(
                    (new_list[i][0] - initial_list[i][0])
                    for i in range(len(new_list))
                ) / len(new_list)
                print(time.time(), 'Horizonal distance:', horiz_dist)

    print(time.time() - start)
