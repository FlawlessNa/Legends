import cv2
import numpy as np
import pytesseract

from abc import ABC, abstractmethod
from functools import cached_property
from royals.utilities import Box, take_screenshot


class InGameBaseVisuals(ABC):
    """Base class for in-game visuals. Contains methods for reading text, detecting colors or images in the game window."""

    def __init__(self, handle: int) -> None:
        self.handle = handle

    @abstractmethod
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass

    def read_from_box(self, box: Box, config: str | None = None) -> str:
        img = take_screenshot(self.handle, box)
        processed = self._preprocess_img(img)
        return self.read_from_img(processed, config)

    def read_from_img(self, image: np.ndarray, config: str | None = None) -> str:
        img = self._preprocess_img(image)
        assert np.unique(img).size == 2, "Image is not binary"
        return pytesseract.image_to_string(img, lang="eng", config=config)

    @staticmethod
    def _color_detection(
        detection_img: np.ndarray,
        needle_color: tuple[tuple, tuple],
        pixel_threshold: int = 0,
    ) -> bool:
        """
        Detects a color in a box.
        :param detection_img: Image in which to detect the color.
        :param needle_color: Lower and upper bounds for the color to be detected.
        :param pixel_threshold: Amount of pixels that need to be detected for the color to be considered present. Defaults to 0.
        :return: Whether the color was detected or not, based on the pixel threshold.
        """
        detection_array = cv2.inRange(detection_img, *needle_color)
        return np.count_nonzero(detection_array) > pixel_threshold

    @staticmethod
    def _needle_detection(
        detection_img: np.ndarray,
        needle_img: np.ndarray,
        threshold: float = 0.99,
        method: int = cv2.TM_CCORR_NORMED,
    ) -> bool:
        """
        Detects a needle image in a haystack image.
        :param detection_img: Image in which to detect the needle.
        :param needle_img: Image to be detected.
        :param threshold: Threshold for the detection. Defaults to 0.99.
        :return: Whether the needle was detected or not, based on the threshold.
        """
        res = cv2.matchTemplate(detection_img, needle_img, method)
        return np.max(res) > threshold


class InGameToggleableVisuals(InGameBaseVisuals):
    @abstractmethod
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass

    def is_displayed(self) -> bool:
        pass


class InGameDynamicVisuals(InGameToggleableVisuals):
    @abstractmethod
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass

    @cached_property
    def _menu_icon_position(self) -> Box:
        pass

    def reset_menu_icon_position(self) -> None:
        self.__dict__.pop("_menu_icon_position", None)
