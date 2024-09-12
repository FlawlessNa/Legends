import cv2
import os
import time
from botting.utilities import take_screenshot, Box

REGION_OF_INTEREST: Box | None = None
HANDLE: int = 0
DESIRED_NUMBER_OF_IMAGES: int = 150
DELAY_BETWEEN_IMAGES: float = 0.5
OUTPUT_FOLDER: str = 'data/character_detection_images'
PREFIX: str = 'character'

if __name__ == '__main__':
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    for i in range(DESIRED_NUMBER_OF_IMAGES):
        image = take_screenshot(HANDLE, REGION_OF_INTEREST)
        cv2.imwrite(os.path.join(OUTPUT_FOLDER, f'{PREFIX}{i}.png'), image)
        HANDLE += 1
        time.sleep(DELAY_BETWEEN_IMAGES)
