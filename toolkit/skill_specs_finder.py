import os
import time

import cv2
import numpy as np
import win32gui

from botting.utilities import Box, take_screenshot
from maple.model.characters import ALL_BUFFS, MapleSkill
from maple.screen.client import find_client

IGN = "WrongDoor"
HANDLE = find_client()
SKILL_NAME = "Meso Up"

skill = ALL_BUFFS[SKILL_NAME]
_, t, r, _ = win32gui.GetClientRect(HANDLE)
buff_region = Box(left=r - 350, top=t + 45, right=r, bottom=85)
icons_directory = MapleSkill.icon_path
buff_icon = cv2.imread(os.path.join(icons_directory, f"{skill.name}.png"))


def process_img(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    return processed


processed_icon = process_img(buff_icon)


if __name__ == "__main__":
    while True:
        client_img = take_screenshot(HANDLE)
        # haystack = buff_region.extract_client_img(client_img)
        # processed_haystack = process_img(haystack)
        processed_haystack = process_img(client_img[:500])
        results = cv2.matchTemplate(
            processed_haystack, processed_icon, cv2.TM_CCOEFF_NORMED
        )
        _, max_val, _, max_loc = cv2.minMaxLoc(results)
        left, top = max_loc
        width, height = processed_icon.shape[::-1]
        cv2.rectangle(
            client_img, (left, top), (left + width, top + height), (0, 0, 255), 2
        )
        target = processed_haystack[top : top + height, left : left + width]
        cv2.imshow("Client", client_img)
        cv2.waitKey(1)
        freshness = (target == processed_icon).sum() / target.size
        print(SKILL_NAME, "Template Match:", max_val, "Freshness Score:", freshness)
        time.sleep(1)
