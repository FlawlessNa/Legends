import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class Bubbling(BaseMob):
    _hsv_lower = np.array([101, 48, 153])
    _hsv_upper = np.array([113, 255, 255])
    _minimal_rect_height = 25
    _minimal_rect_area = 350
    _maximal_rect_area = 5000
    _multiplier = 1

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, cls._hsv_lower, cls._hsv_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> filter:
        def cond1(contour):
            return (
                cls._minimal_rect_area
                < cv2.contourArea(contour)
                < cls._maximal_rect_area
            )

        def cond2(contour):
            return cv2.boundingRect(contour)[-1] > cls._minimal_rect_height

        return filter(lambda cnt: cond1(cnt) and cond2(cnt), contours)
