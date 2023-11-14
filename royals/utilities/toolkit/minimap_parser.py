"""
Helper script to continuously record minimap positioning and record platform endpoints, portals, ladders, etc. based on key presses.
"""
import cv2
import keyboard
import math
import os

from paths import ROOT

from royals.game_interface.dynamic_components.minimap import Minimap
from royals.utilities import take_screenshot, Box

HANDLE = 0x00620DFE
OUTPUT_LOCATION = os.path.join(ROOT, "royals/game_model/maps/")
OUTPUT_NAME = "kerning_line1_area1.py"
JUMP_DIST = 6

container = []


def take_position(minimap: Minimap) -> None:
    pt = minimap.get_character_positions()
    assert len(pt) == 1
    pt = pt.pop()
    print(pt)
    container.append(pt)


def write_feature(cont: list) -> None:
    if len(cont) == 2:
        pt1 = cont.pop(0)
        pt2 = cont.pop(0)
        feature_name = input("Feature name: ")
        box = Box(
            left=int(min(pt1[0], pt2[0])),
            right=int(max(pt1[0], pt2[0])),
            top=math.floor(min(pt1[1], pt2[1]) - JUMP_DIST),
            bottom=math.ceil(max(pt1[1], pt2[1])),
            name=feature_name,
            offset=True
        )
        with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), "a") as f:
            f.write(f"\t@cached_property\n")
            f.write(f"\tdef {feature_name}(self) -> Box:\n")
            f.write(f"\t\treturn {repr(box)}\n")
            f.write("\n")


if __name__ == "__main__":
    minimap = Minimap(HANDLE)

    with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), "w") as f:
        f.write("from functools import cached_property\n")
        f.write("\n")
        f.write("from .base_map import BaseMap\n")
        f.write("from royals.utilities import Box\n")
        f.write("\n")
        f.write("\n")
        f.write(
            f'class {OUTPUT_NAME.removesuffix(".py").replace("_", " ").title().replace(" ", "")}(BaseMap):\n'
        )
        f.write("\n")

    keyboard.on_press_key("z", lambda _: take_position(minimap))
    keyboard.on_press_key("z", lambda _: write_feature(container))
    keyboard.wait()
