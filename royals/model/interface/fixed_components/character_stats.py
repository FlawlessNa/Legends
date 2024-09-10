import cv2
import numpy as np
import string

from botting.visuals import InGameBaseVisuals
from botting.utilities import Box, take_screenshot


class CharacterStats(InGameBaseVisuals):
    """
    Implements character-related UI components (the bottom-left section of the on-screen fixed UI).
    # TODO - Use kernels to detect special characters found within HP and MP -- []/ -- text boxes, and crop boxes accordingly. This should enhance OCR accuracy.
    """

    level_box: Box = Box(
        name="Level",
        left=35,
        right=83,
        top=767,
        bottom=787,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}",
    )
    job_box: Box = Box(
        name="Job",
        left=85,
        right=235,
        top=760,
        bottom=777,
        config=f"--psm 7 -c tessedit_char_whitelist={string.ascii_letters}",
    )
    ign_box: Box = Box(
        name="IGN",
        left=85,
        right=206,
        top=776,
        bottom=793,
        config=f"--psm 7 -c tessedit_char_whitelist={string.ascii_letters}{string.digits}",
    )

    hp_bar_box: Box = Box(name="HP Bar", left=248, right=367, top=779, bottom=790)
    hp_digits_box: Box = Box(
        name="HP Left",
        left=263,
        right=370,
        top=764,
        bottom=774,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}/",
    )

    mp_bar_box: Box = Box(name="MP Bar", left=373, right=498, top=776, bottom=790)
    mp_digits_box: Box = Box(
        name="MP Left",
        left=395,
        right=498,
        top=763,
        bottom=775,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}/",
    )

    exp_bar_box: Box = Box(name="EXP Bar", left=507, right=632, top=776, bottom=790)
    exp_digits_box: Box = Box(
        name="EXP",
        left=528,
        right=642,
        top=764,
        bottom=774,
        config=f"--psm 7 -c tessedit_char_whitelist={string.digits}.%",
    )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if gray.shape == (self.level_box.height, self.level_box.width):
            gray = cv2.inRange(gray, np.array([255]), np.array([255]))
            # gray = cv2.resize(gray, None, fx=10, fy=10)
        return gray

    def get_ign(self, handle: int) -> str:
        return self.read_from_box(handle, self.ign_box, confidence_level=0)

    def get_level(self, handle: int) -> int:
        img = take_screenshot(handle, self.level_box)
        try:
            return int(
                self.read_from_img(
                    img,
                    config="--psm 7 -c tessedit_char_whitelist=0123456789",
                    confidence_level=0,
                )
            )
        except ValueError:
            return 0

    def get_job(self, handle: int) -> str:
        return self.read_from_box(handle, self.job_box, confidence_level=0)
