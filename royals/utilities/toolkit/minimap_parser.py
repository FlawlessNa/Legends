"""
Helper script to continuously record minimap positioning and record platform endpoints, portals, ladders, etc. based on key presses.
"""
import cv2
import os

from paths import ROOT

from royals.game_interface.dynamic_components.minimap import Minimap
from royals.utilities import take_screenshot

HANDLE = 0x00620DFE
OUTPUT_LOCATION = os.path.join(ROOT, "royals/game_model/maps/")
OUTPUT_NAME = 'kerning_line1_area1.py'

if __name__ == "__main__":
    minimap = Minimap(HANDLE)
    with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), 'w') as f:
        f.write('from .base_map import BaseMap')
        f.write('\n')
        f.write('\n')
        f.write(f'class {OUTPUT_NAME.replace("_", " ").title().replace(" ", "")}(BaseMap):')
        f.write('\n')

        while True:
            feature_name = input("Feature name: ")
            f.write(f'def {feature_name}(self):')
            current_pos = minimap.get_character_positions()
            # TODO - Continuously loop until a registering key is pressed, then write coordinates into file
