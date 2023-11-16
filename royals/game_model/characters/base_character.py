import cv2
import numpy as np

from abc import ABC
from typing import Sequence

from royals.game_interface import InGameBaseVisuals
from botting.utilities import Box


class BaseCharacter(InGameBaseVisuals, ABC):
    """
    Base class for all characters.
    Defines general detection methods used for on-screen character detection.
    """

    # Basically the whole screen minus the menus at the bottom
    detection_box_large = Box(left=3, right=1027, top=29, bottom=725)
    detection_box_small = NotImplemented

    def __init__(self, handle: int):
        super().__init__(handle)
        self.ign = self.__class__.__name__
        if self._large_client:
            self.detection_box = self.detection_box_large
        else:
            self.detection_box = self.detection_box_small

    def get_character_position(self, image: np.ndarray) -> Sequence[int] | None:
        processed = self._preprocess_img(image)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            return cv2.boundingRect(max(contours, key=cv2.contourArea))


class FarmFest1(BaseCharacter):
    _hsv_lower = np.array([15, 116, 170])
    _hsv_upper = np.array([18, 181, 188])

    def __init__(self, handle: int) -> None:
        super().__init__(handle)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, self._hsv_lower, self._hsv_upper)
        return binary


if __name__ == "__main__":
    HANDLE = 0x00620DFE
    char = FarmFest1(HANDLE)
    from botting.utilities import take_screenshot

    while True:
        img = take_screenshot(HANDLE, char.detection_box)
        x, y, w, h = char.get_character_position(img)
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), thickness=2)
        cv2.imshow("test", img)
        cv2.waitKey(1)
