import cv2
import os
import time
from paths import ROOT
from botting.utilities import take_screenshot, Box

REGION_OF_INTEREST: Box | None = None
HANDLE: int = 0x01290906
DESIRED_NUMBER_OF_IMAGES: int = 50
DELAY_BETWEEN_IMAGES: float = 2.0
OUTPUT_FOLDER: str = "data/character_detection_images/GS2MobsAndChar/images"
PREFIX: str = "gs2_char_and_mobs"

if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, OUTPUT_FOLDER), exist_ok=True)
    for i in range(DESIRED_NUMBER_OF_IMAGES):
        image = take_screenshot(HANDLE, REGION_OF_INTEREST)
        cv2.imwrite(os.path.join(ROOT, OUTPUT_FOLDER, f"{PREFIX}{i}.png"), image)
        time.sleep(DELAY_BETWEEN_IMAGES)
