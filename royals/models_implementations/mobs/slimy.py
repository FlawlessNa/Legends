import cv2
import numpy as np

from botting.models_abstractions import BaseMob
from botting.utilities import Box


class Slimy(BaseMob):
    _hsv_lower = np.array([53, 58, 219])
    _hsv_upper = np.array([62, 81, 246])
    _minimal_rect_height = 4
    _minimal_rect_width = 6
    _maximal_rect_width = 15
    _multiplier = 4

    def __init__(self, detection_box: Box):
        super().__init__(detection_box)

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, cls._hsv_lower, cls._hsv_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> tuple:
        def cond1(cnt):
            return cls._minimal_rect_height <= cv2.boundingRect(cnt)[-1]

        def cond2(cnt):
            return (
                cls._minimal_rect_width
                <= cv2.boundingRect(cnt)[-2]
                <= cls._maximal_rect_width
            )

        return tuple(filter(lambda cnt: cond1(cnt) and cond2(cnt), contours))
