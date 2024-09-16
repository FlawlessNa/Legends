import asyncio
import cv2
import os
import numpy as np
import win32gui
from botting import controller
from botting.utilities import client_handler, Box, take_screenshot, find_image
from royals import royals_ign_finder
from paths import ROOT
from royals.model.minimaps import PathOfTime1Minimap

from royals.model.characters import Bishop
from royals.model.mechanics.movement_mechanics import Movements
from royals.actions.skills_related_v2 import cast_skill
from royals.actions.movements_v2 import telecast

HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
img_dir = os.path.join(ROOT, "royals/assets/detection_images")

if __name__ == "__main__":
    minimap = PathOfTime1Minimap()
    minimap.generate_grid_template(False)
    moves = Movements("StarBase", HANDLE, None, minimap)
    while True:
        char_pos = minimap.get_character_positions(HANDLE).pop()
        moves.compute_path(char_pos, (20, 20))