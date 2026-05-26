import asyncio
import cv2
import os
import numpy as np
import win32gui
from botting import controller
from botting.utilities import client_handler, Box, take_screenshot, find_image
from maple import maple_ign_finder
from paths import ROOT
from maple.model.minimaps import PathOfTime1Minimap, MysteriousPath3Minimap

from maple.model.characters import Bishop
from maple.model.mechanics.movement_mechanics import Movements
from maple.actions.skills_related_v2 import cast_skill
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