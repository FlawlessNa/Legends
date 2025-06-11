import cv2
import numpy as np

from botting.models_abstractions import BaseMob


class Rodeo(BaseMob):
    _hsv_lower = np.array([136, 77, 50])
    _hsv_upper = np.array([147, 196, 217])
    _minimal_rect_height = 9
    _multiplier = 1.5  # Rodeo - Often a single rect grouped, but sometimes split in two

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, cls._hsv_lower, cls._hsv_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> tuple:
        return tuple(
            filter(
                lambda cnt: cls._minimal_rect_height <= cv2.boundingRect(cnt)[-1],
                contours,
            )
        )
