import cv2
import numpy as np

from botting.models_abstractions import BaseMob
from botting.utilities import Box


class DreamyGhost(BaseMob):
    _color_lower = np.array([152, 102, 255])
    _color_upper = np.array([225, 205, 255])
    _minimal_rect_width = 8
    _minimal_rect_height = 10
    _multiplier = 3

    def __init__(self, detection_box: Box):
        super().__init__(detection_box)

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        binary = cv2.inRange(image, cls._color_lower, cls._color_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> tuple:
        def cond1(cnt):
            return cls._minimal_rect_height <= cv2.boundingRect(cnt)[-1]

        def cond2(cnt):
            return cls._minimal_rect_width <= cv2.boundingRect(cnt)[-2]

        return tuple(filter(lambda cnt: cond1(cnt) and cond2(cnt), contours))
