from abc import ABC, abstractmethod
import cv2
import numpy as np

from typing import Sequence

from botting.models_abstractions import BaseCharacter
from botting.utilities import (
    Box,
    take_screenshot,
    config_reader,
)

from .skills import Skill

DEBUG = False


class Character(BaseCharacter, ABC):
    detection_box_large_client: Box = Box(left=3, right=1027, top=29, bottom=700)
    detection_box_small_client: Box = NotImplemented

    def __init__(self, ign: str, client_size: str) -> None:
        super().__init__(ign)
        self._method = config_reader(
            "character_detection", self.ign, "Detection Method"
        )
        self._detection_params = eval(
            config_reader("character_detection", self.ign, "Detection Parameters")
        )
        self._offset: tuple[int, int] = eval(
            config_reader("character_detection", self.ign, "Detection Offset")
        )
        assert client_size.lower() in ("large", "small")
        self._client_size = client_size

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.ign})"

    def get_onscreen_position(
        self,
        image: np.ndarray | None,
        handle: int = None,
        regions_to_hide: list[Box] = None,
    ) -> tuple[int, int] | None:
        """
        Applies detection method specified through user configs.
        Optionally hides regions of the image (such as minimap) to prevent false positive.
        Optionally applies offset to the detection, as the detection may not be the character itself.
        :param image:
        :param handle:
        :param regions_to_hide:
        :return:
        """
        detection_box = (
            self.detection_box_large_client
            if self._client_size.lower() == "large"
            else self.detection_box_small_client
        )
        if image is None:
            assert handle is not None
            image = take_screenshot(handle, detection_box)

        processed = self._preprocess_img(image)

        if regions_to_hide is not None:
            for region in regions_to_hide:
                processed[region.top : region.bottom, region.left : region.right] = 0

        # Find largest contour
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        largest = max(contours, key=cv2.contourArea)

        moments = cv2.moments(largest)
        if moments["m00"] == 0:
            return None
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])

        if DEBUG:
            _debug(image, largest, cx, cy, self._offset)

        return cx + self._offset[0], cy + self._offset[1]

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        detection_method = self._detection_methods[self._method]
        return detection_method(image, **self._detection_params)

    @property
    @abstractmethod
    def skills(self) -> dict[str, Skill]:
        raise NotImplementedError

    @property
    def _detection_methods(self) -> dict[str, callable]:
        return {
            "Color Filtering": self._apply_color_filtering,
            "HSV Filtering": self._apply_hsv_filtering,
            "Template Matching": self._apply_template_matching,
        }

    @staticmethod
    def _apply_color_filtering(
        image: np.ndarray,
        lower: Sequence[int],
        upper: Sequence[int],
    ) -> np.ndarray:
        return cv2.inRange(image, np.array(lower), np.array(upper))

    def _apply_hsv_filtering(
        self,
        image: np.ndarray,
        lower: Sequence[int],
        upper: Sequence[int],
    ) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        return self._apply_color_filtering(hsv, lower, upper)

    def _apply_template_matching(
        self,
        image: np.ndarray,
        template: np.ndarray,
        threshold: float,
    ) -> np.ndarray:
        raise NotImplementedError


def _debug(image: np.ndarray, contour, cx, cy, offset) -> None:
    # Then draw a rectangle around it
    x, y, w, h = cv2.boundingRect(contour)
    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)
    cv2.circle(image, (cx + offset[0], cy + offset[1]), 5, (0, 0, 255), -1)
    cv2.imshow("_DEBUG_ Character.get_on_screen_position", image)
    cv2.waitKey(1)


if __name__ == "__main__":
    HANDLE = 0x02300A26
    test = Character("FarmFest1", "large")
    while True:
        test.get_onscreen_position(
            None,
            handle=HANDLE,
            regions_to_hide=[Box(left=0, right=275, top=0, bottom=195)],
        )
