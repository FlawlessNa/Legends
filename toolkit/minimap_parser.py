"""
Helper script to continuously record minimap positioning and record platform endpoints, portals, ladders, etc. based on key presses.
"""
import keyboard
import math
import os

import numpy as np

from paths import ROOT

from royals.interface.dynamic_components.minimap import Minimap
from botting.utilities import Box

HANDLE = 0x02300A26
OUTPUT_LOCATION = os.path.join(ROOT, "royals/models_implementations/minimaps/")
OUTPUT_NAME = "test.py"

container = []


class FakeMinimap(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


def take_position(minimap: Minimap) -> None:
    pt = minimap.get_character_positions(HANDLE)
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
            left=math.floor(min(pt1[0], pt2[0])),
            right=math.ceil(max(pt1[0], pt2[0])),
            top=math.floor(min(pt1[1], pt2[1])),
            bottom=math.ceil(max(pt1[1], pt2[1])),
            name=feature_name,
            offset=True
        )
        with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), "a") as f:
            f.write(f"\t{feature_name}: MinimapFeature = MinimapFeature(")
            f.write("\n")
            f.write(f"\t\tleft={box.left},\n")
            f.write(f"\t\tright={box.right},\n")
            f.write(f"\t\ttop={box.top},\n")
            f.write(f"\t\tbottom={box.bottom},\n")
            f.write(f"\t\tname={repr(box.name)},\n")
            f.write("\t)\n")


if __name__ == "__main__":
    minimap = FakeMinimap()

    with open(os.path.join(OUTPUT_LOCATION, OUTPUT_NAME), "w") as f:
        f.write(
"""from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)
    """)
        f.write("\n")
        f.write("\n")
        f.write(
            f'class {OUTPUT_NAME.removesuffix(".py").replace("_", " ").title().replace(" ", "")}(MinimapPathingMechanics):\n'
        )
        f.write("\n")

    keyboard.on_press_key("z", lambda _: take_position(minimap))
    keyboard.on_press_key("z", lambda _: write_feature(container))
    keyboard.wait()
