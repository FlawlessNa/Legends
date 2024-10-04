import cv2
import numpy as np
from abc import ABC
from functools import cached_property

from botting.models_abstractions import BaseCharacter
from botting.utilities import (
    Box,
    take_screenshot,
    config_reader,
)
from royals.model.mechanics import RoyalsSkill

DEBUG = True


class Character(BaseCharacter, ABC):
    """
    Base class for all characters.
    Uses a detection model or a combination of detection methods (specified through
    config files) to detect the character on screen.
    If both the model_path and detection_configs are specified, then both are used
    and the final result is cross-validated.
    """

    detection_box_small_client: Box = NotImplemented
    detection_box_medium_client: Box = Box(left=0, right=1024, top=29, bottom=700)
    detection_box_large_client: Box = NotImplemented
    main_skill: str = NotImplemented
    main_stat: str = NotImplemented
    skills: dict[str, RoyalsSkill] = NotImplemented

    def __init__(
        self,
        ign: str,
        detection_configs: str = None,
        client_size: str = "medium",
    ) -> None:
        super().__init__(ign)

        self._preprocessing_method = None
        self._preprocessing_params = None
        self._detection_methods = None
        self._detection_offset = None
        if detection_configs is not None:
            self._set_detection_configs(detection_configs)
        assert client_size.lower() in ("large", "medium", "small")
        self._client_size = client_size

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.ign})"

    def _set_detection_configs(self, section: str) -> None:
        """
        Sets the detection configs for the character.
        """
        self._preprocessing_method = config_reader(
            "character_detection", section, "Preprocessing Method"
        )
        self._preprocessing_params = eval(
            config_reader("character_detection", section, "Preprocessing Parameters")
        )
        _detection_methods = eval(
            config_reader("character_detection", section, "Detection Methods")
        )
        self._detection_methods = {
            i: eval(config_reader("character_detection", section, f"{i} Parameters"))
            for i in _detection_methods
        }
        self._detection_offset: tuple[int, int] = eval(
            config_reader("character_detection", section, "Detection Offset")
        )

    @cached_property
    def detection_box(self) -> Box:
        if self._client_size == "small":
            return self.detection_box_small_client
        elif self._client_size == "medium":
            return self.detection_box_medium_client
        elif self._client_size == "large":
            return self.detection_box_large_client
        else:
            raise ValueError(f"Invalid client size: {self._client_size}")

    def get_onscreen_position(
        self,
        image: np.ndarray | None,
        handle: int,
        regions_to_hide: list[Box] = None,
        acceptance_threshold: float = None,
    ) -> tuple[int, int, int, int] | None:
        """
        Method used solely to detect a single character on-screen.
        Applies detection method specified through user configs.
        Optionally hides regions of the image (such as minimap) to prevent false positive.
        Optionally applies offset to the detection, as the detection may not be the character itself.
        :param image:
        :param handle:
        :param regions_to_hide:
        :param acceptance_threshold: To use with detection model.
        :return: x1, y1, x2, y2 format for a bounding box.
        """
        res = model_res = detection_res = None
        if image is None:
            assert handle is not None
            image = take_screenshot(handle, self.detection_box)
        else:
            image = image.copy()

        if regions_to_hide is not None:
            for region in regions_to_hide:
                image[region.top : region.bottom, region.left : region.right] = 0

        if self.detection_model is not None:
            if acceptance_threshold is None:
                acceptance_threshold = self.DEFAULT_THRESHOLD
            detections = self.run_detection_model(handle, image, acceptance_threshold)
            model_res = tuple(
                [
                    dct["box"].values() for dct in detections.summary()
                    if dct["name"] == "Character"
                ]
            )
            if len(model_res) > 1:
                breakpoint()  # Multiple characters detected, will need to handle this.

            elif len(model_res) == 1:
                model_res = tuple(map(round, model_res[0]))
                # if DEBUG:
                #     x1, y1, x2, y2 = model_res
                #     cv2.rectangle(image, (x1, y1), (x2, y2), (255, 0, 0), 3)

        if self._detection_methods is not None:
            detection_res = self._run_detection_methods(image, "single")
            if detection_res is not None:
                detection_res = detection_res[0]
                if DEBUG:
                    x, y, w, h = detection_res
                    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 3)

        if self.detection_model is not None and self._detection_methods is not None:
            res = self._cross_validate_results(model_res, detection_res)  # noqa
        elif self.detection_model is not None:
            res = model_res
        elif self._detection_methods is not None:
            res = detection_res

        # if DEBUG:
        #     if res is not None:
        #         x1, y1, x2, y2 = res
        #         cv2.rectangle(image, (x1, y1), (x2, y2), (255, 255, 255), 3)
        #     cv2.imshow("_DEBUG_ Character.get_on_screen_position", image)
        #     cv2.waitKey(1)
        return res

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        detection_method = self._preprocessing_functions[self._preprocessing_method]
        return detection_method(image, **self._preprocessing_params)

    def _run_detection_model(
        self, image: np.ndarray, acceptance_threshold: float, mode: str
    ) -> list[tuple[float, float, float, float]]:
        """
        Runs the detection model on the image.
        """
        result = []
        for res in self.detection_model(
            image,
            conf=acceptance_threshold,
            max_det=1 if mode == "single" else 100,
            verbose=False
        ):
            result.extend(
                tuple(dct["box"].values())
                for dct in res.summary()
                if dct["name"] == "Character"
            )
        return result or None

    def _run_detection_methods(
        self, image: np.ndarray, mode: str
    ) -> list[tuple[int, int, int, int]] | None:
        """
        Runs the detection methods on the image.
        """
        processed = self._preprocess_img(image)
        largest = res = None
        if "Contour Detection" in self._detection_methods:
            res = self._apply_contour_detection(
                processed, **self._detection_methods["Contour Detection"]
            )
            if len(res):
                largest = cv2.boundingRect(max(res, key=cv2.contourArea))

        if "Bounding Rectangles" in self._detection_methods:
            assert (
                "Contour Detection" in self._detection_methods
            ), "Bounding Rectangles must be used with Contour Detection"
            res = self._apply_bounding_rectangles(
                res, **self._detection_methods["Bounding Rectangles"]
            )
            if len(res):
                largest = max(res, key=lambda x: x[2] * x[3])

        if "Rectangle Grouping" in self._detection_methods:
            assert (
                "Bounding Rectangles" in self._detection_methods
            ), "Rectangle Grouping must be used with Bounding Rectangles"
            res = self._apply_rectangle_grouping(
                res, **self._detection_methods["Rectangle Grouping"]
            )
            if len(res):
                largest = max(res, key=lambda x: x[2] * x[3])

        if "Dimension Filtering" in self._detection_methods:
            assert (
                "Bounding Rectangles" in self._detection_methods
            ), "Dimension Filtering must be used with Bounding Rectangles"
            min_w = self._detection_methods["Dimension Filtering"].get("min_width", 0)
            min_h = self._detection_methods["Dimension Filtering"].get("min_height", 0)
            max_w = self._detection_methods["Dimension Filtering"].get(
                "max_width", 9999
            )
            max_h = self._detection_methods["Dimension Filtering"].get(
                "max_height", 9999
            )
            res = [
                rect
                for rect in res
                if min_w <= rect[2] <= max_w and min_h <= rect[3] <= max_h
            ]
            if len(res):
                largest = max(res, key=lambda x: x[2] * x[3])

        # After all pre-processing + detection, if no result, there should not be any largest either.
        if not len(res):
            return None
        return [largest] if mode == "single" else res

    def _cross_validate_results(
        self,
        model_res: tuple[int, int, int, int],
        detection_res: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        """
        Cross-validates the results from the detection model and detection methods.
        """
        if model_res is None or detection_res is None:
            return
        mx1, my1, mx2, my2 = model_res
        dx1, dy1, dw, dh = detection_res
        dx1, dy1 = dx1 + self._detection_offset[0], dy1 + self._detection_offset[1]
        dx2, dy2 = dx1 + dw, dy1 + dh

        # Check if the two rectangles intersect
        x = max(mx1, dx1)
        y = max(my1, dy1)
        w = min(mx2, dx2) - x
        h = min(my2, dy2) - y
        if not (w > 0 and h > 0):
            return None
        else:
            # Return the outermost rectangle
            return min(mx1, dx1), min(my1, dy1), max(mx2, dx2), max(my2, dy2)

    @property
    def _preprocessing_functions(self) -> dict[str, callable]:
        return {
            "Color Filtering": self._apply_color_filtering,
            "HSV Filtering": self._apply_hsv_filtering,
            "Template Matching": self._apply_template_matching,
        }

    @property
    def _detection_functions(self) -> dict[str, callable]:
        return {
            "Contour Detection": self._apply_contour_detection,
            "Bounding Rectangles": self._apply_bounding_rectangles,
            "Rectangle Grouping": self._apply_rectangle_grouping,
            "Convex Hull": self._apply_convex_hull,
        }
