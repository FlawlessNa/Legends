import cv2
import os
import sys
import keyboard  # Need to install this package to run the data_builder script

from functools import partial
from paths import ROOT
from royals.utilities import take_screenshot

OUTPUT_FOLDER = os.path.join(ROOT, "data/character_detection")
HANDLE = 0x00040E52

if __name__ == "__main__":
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    def take_and_save_image(i):
        img = take_screenshot(HANDLE)
        cv2.imwrite(f"{OUTPUT_FOLDER}/image_{len(os.listdir(OUTPUT_FOLDER))}.png", img)
        print(
            f"Saved image to {OUTPUT_FOLDER}/image_{len(os.listdir(OUTPUT_FOLDER))}.png"
        )

    keyboard.on_press_key("z", take_and_save_image)
    keyboard.on_press_key("q", sys.exit)
    keyboard.wait()
