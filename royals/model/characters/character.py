import cv2
import numpy as np
import os
from abc import ABC
from functools import cached_property
from ultralytics import YOLO

from botting.models_abstractions import BaseCharacter
from botting.utilities import (
    Box,
    take_screenshot,
    config_reader,
)
from paths import ROOT
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
        model_path: str = None,
        detection_configs: str = None,
        client_size: str = "medium"
    ) -> None:
        super().__init__(ign)

        if model_path is not None:
            if not os.path.exists(model_path):
                _model_path = os.path.join(ROOT, model_path)
            assert os.path.exists(model_path), f"Model {model_path} does not exist."
        self._model_path = model_path

        self._preprocessing_method = None
        self._preprocessing_params = None
        self._detection_methods = None
        self._offset = None
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
        self._offset: tuple[int, int] = eval(
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

    @cached_property
    def detection_model(self) -> YOLO | None:
        if self._model_path is not None:
            return YOLO(self._model_path, task='detect')

    def get_onscreen_position(
        self,
        image: np.ndarray | None,
        handle: int = None,
        regions_to_hide: list[Box] = None,
        acceptance_threshold: float = None,
    ) -> tuple[int, int] | None:
        """
        Applies detection method specified through user configs.
        Optionally hides regions of the image (such as minimap) to prevent false positive.
        Optionally applies offset to the detection, as the detection may not be the character itself.
        :param image:
        :param handle:
        :param regions_to_hide:
        :param acceptance_threshold: To use with detection model.
        :return:
        """
        res = None
        if image is None:
            assert handle is not None
            image = take_screenshot(handle, self.detection_box)
        else:
            image = image.copy()

        if regions_to_hide is not None:
            for region in regions_to_hide:
                image[region.top : region.bottom, region.left : region.right] = 0

        if self.detection_model is not None:
            model_res = self._run_detection_model(image, acceptance_threshold)

        if self._detection_methods is not None:
            detection_res = self._run_detection_methods(image, regions_to_hide)
        processed = self._preprocess_img(image)

        if regions_to_hide is not None:
            for region in regions_to_hide:
                processed[region.top : region.bottom, region.left : region.right] = 0

        largest = None
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
            largest = None
        #
        # # Cross-validate both rectangles, if a model is used
        # if self._model is not None:
        #     rects, lvls, weights = self._model.detectMultiScale3(
        #         image, 1.1, 6, 0, (50, 50), (90, 90), True
        #     )
        #     if len(weights) and largest is not None:
        #         max_conf = np.argmax(weights)
        #         (x, y, w, h) = rects[max_conf]
        #         if DEBUG:
        #             cv2.rectangle(image, (x, y), (x + w, y + h), (255, 0, 0), 2)
        #
        #         cnt_x, cnt_y, cnt_w, cnt_h = largest
        #         cnt_x += self._offset[0]
        #         cnt_y += self._offset[1]
        #         xi = max(x, cnt_x)
        #         yi = max(y, cnt_y)
        #         wi = min(x + w, cnt_x + cnt_w) - xi
        #         hi = min(y + h, cnt_y + cnt_h) - yi
        #         if not (wi > 0 and hi > 0):
        #             return None

        cx = None
        cy = None
        if largest is not None:
            x, y, w, h = largest
            cx, cy = int(x + w // 2), int(y + h // 2)

        if DEBUG:
            _debug(image, largest, cx, cy, self._offset)

        if cx is not None and cy is not None:
            return (
                cx + self._offset[0] + self.detection_box.left,
                cy + self._offset[1] + self.detection_box.top,
            )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        detection_method = self._preprocessing_functions[self._preprocessing_method]
        return detection_method(image, **self._preprocessing_params)

    def _run_detection_model(
        self, image: np.ndarray, acceptance_threshold: float
    ) -> list[tuple[int, int, int, int]]:
        """
        Runs the detection model on the image.
        """
        results = self.detection_model(image)
        res = []
        breakpoint()
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy.numpy().astype(int).squeeze()
                cls = box.cls.numpy()[0]
                conf = box.conf.numpy()[0]
                if acceptance_threshold is not None and conf < acceptance_threshold:
                    continue
                res.append((x1, y1, x2 - x1, y2 - y1))
        return res

    def _run_detection_methods(
        self, image: np.ndarray, regions_to_hide: list[Box]
    ) -> list[tuple[int, int, int, int]]:
        """
        Runs the detection methods on the image.
        """
        res = []
        for method, params in self._detection_methods.items():
            detection_method = self._detection_functions[method]
            res = detection_method(image, regions_to_hide, **params)
        return res

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


def _debug(image: np.ndarray, rect, cx, cy, offset) -> None:
    # Then draw a rectangle around it
    if rect is not None:
        x, y, w, h = rect
        x += offset[0]
        y += offset[1]
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.circle(image, (cx + offset[0], cy + offset[1]), 5, (0, 0, 255), -1)
    cv2.imshow("_DEBUG_ Character.get_on_screen_position", image)
    cv2.waitKey(1)
