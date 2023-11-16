import cv2
import numpy as np

from abc import ABC, abstractmethod
from typing import Sequence

from royals.game_interface import InGameBaseVisuals
from botting.utilities import Box


class BaseMob(InGameBaseVisuals, ABC):
    """
    Base class for all in-game Mobs.
    Defines general detection methods used for on-screen mob detection.
    """

    # Basically the whole screen minus the menus at the bottom
    detection_box_large = Box(left=3, right=1027, top=29, bottom=725)
    detection_box_small = NotImplemented

    def __init__(self, handle: int) -> None:
        super().__init__(handle)
        if self._large_client:
            self.detection_box = self.detection_box_large
        else:
            self.detection_box = self.detection_box_small

    @classmethod
    @abstractmethod
    def _filter(cls, contours) -> list[np.ndarray]:
        """
        Filters the contours found in the image to only return the ones assumed to be "mob-like".
        """
        pass

    def get_onscreen_mobs(self, image: np.ndarray) -> list[Sequence[int]]:
        """
        Returns a list of tuples containing the coordinates of the mobs found on-screen.
        :return: Coordinates are, in order, x, y, width, height.
        """
        processed = self._preprocess_img(image)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return [cv2.boundingRect(cnt) for cnt in self._filter(contours)]

    def get_mob_count(self, image: np.ndarray) -> int:
        """
        Returns the number of mobs found on-screen.
        """
        return len(self.get_onscreen_mobs(image))
