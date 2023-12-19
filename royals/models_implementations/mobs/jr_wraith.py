import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class JrWraith(BaseMob):
    _hsv_lower = np.array([0, 0, 193])
    _hsv_upper = np.array([179, 255, 255])
    # _minimal_rect_height = 25
    _minimal_rect_area = 675
    _maximal_rect_area = 725

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
        #
        # def cond2(contour):
        #     return cv2.boundingRect(contour)[-1] > cls._minimal_rect_height
        return filter(lambda cnt: cond1(cnt), contours)
        # return filter(lambda cnt: cond1(cnt) and cond2(cnt), contours)
