import os
from botting.utilities import client_handler
from royals import royals_ign_finder
from paths import ROOT
from maple._old.minimaps import MysteriousPath3Minimap

from maple._old.movement_mechanics import Movements
from maple.actions.movements_v2 import telecast

HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
img_dir = os.path.join(ROOT, "maple/assets/detection_images")

if __name__ == "__main__":
    minimap = MysteriousPath3Minimap()
    minimap.generate_grid_template(True)
    moves = Movements("StarBase", HANDLE, None, minimap)
    while True:
        char_pos = minimap.get_character_positions(HANDLE).pop()
        print(char_pos)
        moves.compute_path(char_pos, (20, 20))