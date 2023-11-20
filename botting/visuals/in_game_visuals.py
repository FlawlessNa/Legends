"""
Base classes for in-game visuals. Contains methods for reading text, detecting colors or images in the game window.
"""
import cv2
import numpy as np
import pytesseract

from abc import ABC, abstractmethod

from botting.utilities import Box, take_screenshot, find_image


class InGameBaseVisuals(ABC):
    """
    Base class for in-game visuals.
    Should be used for any on-screen component that is "fixed" in game, meaning that it will always be in the same position.
    """

    @abstractmethod
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        For visuals that may contain characters, this method can be used to preprocess the image before it is passed to pytesseract.
        Otherwise, it can also be preprocessed for enhancing detection of objects.
        :param image: The image to process.
        :return: Processed image.
        """
        pass

    def read_from_box(
        self,
        handle: int,
        box: Box,
        config: str | None = None,
        confidence_level: int = 15,
    ) -> str:
        """
        Takes a screenshot of the provided region (box) in the window associated to the handle, and reads text from it.
        :param handle: The handle to the game client window.
        :param box: A box defining the on-screen area to read from.
        :param config: Any additional configuration for pytesseract, which may improve its accuracy. If not provided, use box.config.
        :param confidence_level: The minimum confidence level for a character to be considered valid. Defaults to 15 (this is quite low).
        :return: string that was read by pytesseract.
        """
        img = take_screenshot(handle, box)
        if config is None:
            config = box.config
        return self.read_from_img(img, config, confidence_level)

    def read_from_img(
        self, image: np.ndarray, config: str | None = None, confidence_level: int = 15
    ) -> str:
        """
        Reads text from an image. It pre-processes the image before passing it to pytesseract.
        :param image: The raw image to read from.
        :param config: Any additional configuration for pytesseract, which may improve its accuracy.
        :param confidence_level: The minimum confidence level for a character to be considered valid. Defaults to 15 (this is quite low).
        :return:
        """
        img = self._preprocess_img(image)
        result = pytesseract.image_to_data(
            img, lang="eng", config=config, output_type=pytesseract.Output.DICT
        )
        filtered_res = [
            result["text"][i]
            for i in range(len(result["text"]))
            if int(result["conf"][i]) > confidence_level
        ]
        return " ".join(filtered_res)

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


class InGameToggleableVisuals(InGameBaseVisuals, ABC):
    """
    Base class for in-game visuals that can be toggled on and off (usually through a keybind or mouse click).
    """
    @abstractmethod
    def is_displayed(self, handle: int) -> bool:
        """
        Checks whether the visual is currently displayed on screen. Must be implemented for each visual child class.
        This can be done through color detection, image detection, or any detection method.
        :param handle: Handle to the game client.
        :return: Whether the visual is currently displayed on screen. Note that if the visual is obstructed, this may return False.
        """
        pass


class InGameDynamicVisuals(InGameToggleableVisuals, ABC):
    """
    Base class for a visual that is dynamic, meaning that it can be moved around the screen.
    Child class should define a detection image (saved in the assets/ folder) that will be used to detect the visual.
    This image can be only a small portion of the visual, as long as it is unique enough to be detected.
    The detection is made through templateMatching. If the visual is obstructed, it may not be properly detected.
    """
    _menu_icon_detection_needle: np.ndarray

    def _menu_icon_position(self, handle: int, client_img: np.ndarray | None = None) -> Box | None:
        """
        Use the detection image to find the menu icon position.
        Child classes can use the result of this method to pinpoint the entire visual.
        :param handle: Handle to the game client.
        :param client_img: If provided, use this image. Otherwise, take a screenshot of the entire client.
        :return: Box coordinates of the menu icon.
        """
        if client_img is None:
            client_img = take_screenshot(handle)
        boxes = find_image(client_img, self._menu_icon_detection_needle)
        if len(boxes) > 1:
            raise ValueError("More than one menu icon detected")
        elif boxes:
            return boxes.pop()
