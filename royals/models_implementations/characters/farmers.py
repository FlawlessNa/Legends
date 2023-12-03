import cv2
import numpy as np

from typing import Sequence

from botting.models_abstractions import BaseCharacter
from botting.utilities import Box


class FarmFest1(BaseCharacter):
    detection_box = Box(left=3, right=1027, top=29, bottom=725)
    _hsv_lower = np.array([15, 116, 170])
    _hsv_upper = np.array([18, 181, 188])

    def __init__(self, skills) -> None:
        super().__init__(skills)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, self._hsv_lower, self._hsv_upper)
        return binary

    def get_character_position(self, image: np.ndarray) -> Sequence[int] | None:
        processed = self._preprocess_img(image)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            return cv2.boundingRect(max(contours, key=cv2.contourArea))
