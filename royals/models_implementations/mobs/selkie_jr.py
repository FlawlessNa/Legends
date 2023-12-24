import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class SelkieJr(BaseMob):
    _color_lower = np.array([0, 0, 0])
    _color_upper = np.array([33, 75, 59])
    _minimal_rect_width = 68
    _minimal_rect_height = 65
    _maximal_rect_width = 114
    _maximal_rect_height = 135

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        binary = cv2.inRange(image, cls._color_lower, cls._color_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> tuple:
        def cond1(cnt):
            return (
                cls._minimal_rect_height
                <= cv2.boundingRect(cnt)[-1] <= cls._maximal_rect_height
            )

        def cond2(cnt):
            return (
                cls._minimal_rect_width
                <= cv2.boundingRect(cnt)[-2] <= cls._maximal_rect_width
            )

        return filter(cond1 and cond2, contours)



