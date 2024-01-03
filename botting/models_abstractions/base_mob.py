import cv2
import numpy as np

from abc import ABC, abstractmethod
from typing import Sequence

from botting.utilities import Box
from botting.visuals import InGameBaseVisuals


class BaseMob(InGameBaseVisuals, ABC):
    """
    Base class for all in-game Mobs.
    Defines contour detection method used for on-screen mob detection.
    This behavior can be overridden by the inheriting class.
    """
    _hsv_lower: np.ndarray = NotImplemented
    _hsv_upper: np.ndarray = NotImplemented
    _color_lower: np.ndarray = NotImplemented
    _color_upper: np.ndarray = NotImplemented

    _minimal_rect_height: int = NotImplemented
    _maximal_rect_height: int = NotImplemented
    _minimal_rect_width: int = NotImplemented
    _maximal_rect_width: int = NotImplemented
    _minimal_rect_area: int = NotImplemented
    _maximal_rect_area: int = NotImplemented

    def __init__(self, detection_box: Box):
        self.detection_box = detection_box

    @classmethod
    @abstractmethod
    def _filter(cls, contours) -> list[np.ndarray]:
        """
        Filters the contours found to only return the ones assumed to be "mob-like".
        """
        pass

    def get_onscreen_mobs(self, image: np.ndarray) -> list[Sequence[int]]:
        """
        Returns a list of tuples of the coordinates for each mob found on-screen.
        :return: Coordinates are, in order, x, y, width, height.
        """
        processed = self._preprocess_img(image)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        try:
            return [cv2.boundingRect(cnt) for cnt in self._filter(contours)]
        except Exception as e:
            breakpoint()

    def get_mob_count(self, image: np.ndarray) -> int:
        """
        Returns the number of mobs found on-screen.
        """
        return len(self.get_onscreen_mobs(image))
