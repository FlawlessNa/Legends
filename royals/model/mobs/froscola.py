import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class Froscola(BaseMob):
    pass
    _hsv_lower = np.array([174, 255, 116])
    _hsv_upper = np.array([179, 255, 255])
    _minimal_rect_height = 10
    _minimal_rect_width = 10
    _multiplier = 2

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
            return cls._minimal_rect_width <= cv2.boundingRect(cnt)[-2]

        return tuple(filter(lambda cnt: cond1(cnt) and cond2(cnt), contours))