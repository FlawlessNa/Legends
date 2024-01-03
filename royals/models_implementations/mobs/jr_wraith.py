import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class JrWraith(BaseMob):
    # _hsv_lower = np.array([0, 0, 193])
    # _hsv_upper = np.array([179, 255, 255])
    _color_lower = np.array([68, 68, 51])
    _color_upper = np.array([68, 68, 51])
    # _minimal_rect_height = 25
    _minimal_rect_area = 10
    _maximal_rect_area = 90

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        binary = cv2.inRange(image, cls._color_lower, cls._color_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> filter:
        def cond1(contour):
            return (
                cls._minimal_rect_area
                <= cv2.contourArea(contour)
                <= cls._maximal_rect_area
            )

        rects = [cv2.boundingRect(cnt) for cnt in contours if cond1(cnt)]
        grouped = cv2.groupRectangles(rects, 1, 2)
        grouped_contours = [
            np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
            for x, y, w, h in grouped[0]
        ]

        #
        # def cond2(contour):
        #     return cv2.boundingRect(contour)[-1] > cls._minimal_rect_height
        # return filter(lambda cnt: cond1(cnt), contours)
        return grouped_contours
        # return filter(lambda cnt: cond1(cnt) and cond2(cnt), contours)
