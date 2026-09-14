from abc import ABC
from collections.abc import Callable, Sequence
from functools import cached_property
from typing import Any

import cv2
import numpy as np

from botting.models_abstractions import BaseCharacter
from botting.utilities import (
    Box,
    config_reader,
    take_screenshot,
)

from .maple_skills import MapleSkill

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
    # Narrower than `BaseCharacter.skills`, deliberately: this layer's skills are
    # MapleSkills, and every consumer here relies on that.
    skills: dict[str, MapleSkill] = NotImplemented  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(
        self,
        ign: str,
        detection_configs: str | None = None,
        client_size: str = "medium",
    ) -> None:
        super().__init__(ign)

        self._preprocessing_method: str | None = None
        self._preprocessing_params: dict[str, Any] | None = None
        self._detection_methods: dict[str, dict[str, Any]] | None = None
        self._detection_offset: tuple[int, int] | None = None
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

        def _read(key: str) -> str:
            return str(config_reader("character_detection", section, key))

        self._preprocessing_method = _read("Preprocessing Method")
        self._preprocessing_params = eval(_read("Preprocessing Parameters"))
        _detection_methods = eval(_read("Detection Methods"))
        self._detection_methods = {
            i: eval(_read(f"{i} Parameters")) for i in _detection_methods
        }
        self._detection_offset = eval(_read("Detection Offset"))

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
        regions_to_hide: list[Box] | None = None,
        acceptance_threshold: float | None = None,
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
        model_res: Sequence[int] | None = None
        detection_res: Sequence[int] | None = None
        mask: np.ndarray | None = None
        if image is None:
            assert handle is not None
            image = take_screenshot(handle, self.detection_box)
        else:
            image = image.copy()

        if regions_to_hide is not None:
            mask = np.ones(image.shape, np.uint8) * 255
            for region in regions_to_hide:
                mask[region.top : region.bottom, region.left : region.right] = 0

        if self.detection_model is not None:
            detections = self.run_detection_model(
                handle, image, acceptance_threshold, debug=DEBUG
            )
            found = self.extract_results(detections, mask=mask)

            if len(found) > 1:
                # TODO - Cross validate with VR coordinates and take closest.
                # For now, just return the one with highest confidence.
                best = max(
                    [dct for dct in detections.summary() if dct["name"] == "Character"],
                    key=lambda dct: dct["confidence"],
                )["box"].values()
                model_res = tuple(map(round, best))
            elif len(found) == 1:
                model_res = found[0]

        if self._detection_methods is not None:
            if mask is not None:
                image = cv2.bitwise_and(image, mask)
            found = self._run_detection_methods(image, "single")
            if found:
                detection_res = found[0]
                if DEBUG and detection_res is not None:
                    x, y, w, h = detection_res
                    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 0, 255), 3)
                    cv2.imshow("Detection", image)
                    cv2.waitKey(1)

        res: Sequence[int] | None = None
        if self.detection_model is not None and self._detection_methods is not None:
            res = self._cross_validate_results(model_res, detection_res)
        elif self.detection_model is not None:
            res = model_res
        elif self._detection_methods is not None:
            res = detection_res
        if res is None:
            return None
        x, y, w, h = res
        return int(x), int(y), int(w), int(h)

    def _require_detection_config(
        self,
    ) -> tuple[str, dict[str, Any], dict[str, dict[str, Any]]]:
        """
        The three config-derived attributes, or a message saying they are absent.

        They are read together from one config section, so they are either all
        set or all None. Everything below is reached only when they are set,
        which is a fact no annotation carries across a method boundary.
        """
        if (
            self._preprocessing_method is None
            or self._preprocessing_params is None
            or self._detection_methods is None
        ):
            raise RuntimeError(
                f"{self!r} was built without detection configs, so it cannot run "
                f"the contour-detection pipeline."
            )
        return (
            self._preprocessing_method,
            self._preprocessing_params,
            self._detection_methods,
        )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        method, params, _ = self._require_detection_config()
        return self._preprocessing_functions[method](image, **params)

    def _run_detection_methods(
        self, image: np.ndarray, mode: str
    ) -> list[tuple[int, int, int, int]] | None:
        """
        Runs the detection methods on the image.
        """
        _, _, methods = self._require_detection_config()
        processed = self._preprocess_img(image)
        largest: tuple[int, int, int, int] | None = None
        # An empty sequence rather than None: the tail does `len(res)`, which
        # raised whenever the config had no Contour Detection stage.
        res: Sequence[Any] = []
        if "Contour Detection" in methods:
            res = self._apply_contour_detection(
                processed, **methods["Contour Detection"]
            )
            if len(res):
                box = cv2.boundingRect(max(res, key=cv2.contourArea))
                largest = (box[0], box[1], box[2], box[3])

        if "Bounding Rectangles" in methods:
            assert "Contour Detection" in methods, (
                "Bounding Rectangles must be used with Contour Detection"
            )
            res = self._apply_bounding_rectangles(res, **methods["Bounding Rectangles"])
            if len(res):
                widest = max(res, key=lambda x: x[2] * x[3])
                largest = (widest[0], widest[1], widest[2], widest[3])

        if "Rectangle Grouping" in methods:
            assert "Bounding Rectangles" in methods, (
                "Rectangle Grouping must be used with Bounding Rectangles"
            )
            res = self._apply_rectangle_grouping(
                [tuple(r) for r in res], **methods["Rectangle Grouping"]
            )
            if len(res):
                widest = max(res, key=lambda x: x[2] * x[3])
                largest = (widest[0], widest[1], widest[2], widest[3])

        if "Dimension Filtering" in methods:
            assert "Bounding Rectangles" in methods, (
                "Dimension Filtering must be used with Bounding Rectangles"
            )
            min_w = methods["Dimension Filtering"].get("min_width", 0)
            min_h = methods["Dimension Filtering"].get("min_height", 0)
            max_w = methods["Dimension Filtering"].get("max_width", 9999)
            max_h = methods["Dimension Filtering"].get("max_height", 9999)
            res = [
                rect
                for rect in res
                if min_w <= rect[2] <= max_w and min_h <= rect[3] <= max_h
            ]
            if len(res):
                widest = max(res, key=lambda x: x[2] * x[3])
                largest = (widest[0], widest[1], widest[2], widest[3])

        # After all pre-processing + detection, if no result, there should not be any largest either.
        if not len(res):
            return None
        if largest is None:
            return None
        return [largest] if mode == "single" else [tuple(r) for r in res]  # type: ignore[return-value]

    def _cross_validate_results(
        self,
        model_res: Sequence[int] | None,
        detection_res: Sequence[int] | None,
    ) -> tuple[int, int, int, int] | None:
        """
        Cross-validates the results from the detection model and detection methods.
        """
        if model_res is None or detection_res is None:
            return None
        assert self._detection_offset is not None, (
            "Cross-validation needs the detection offset from the config section."
        )
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
    def _preprocessing_functions(self) -> dict[str, Callable[..., Any]]:
        return {
            "Color Filtering": self._apply_color_filtering,
            "HSV Filtering": self._apply_hsv_filtering,
            "Template Matching": self._apply_template_matching,
        }

    @property
    def _detection_functions(self) -> dict[str, Callable[..., Any]]:
        return {
            "Contour Detection": self._apply_contour_detection,
            "Bounding Rectangles": self._apply_bounding_rectangles,
            "Rectangle Grouping": self._apply_rectangle_grouping,
            "Convex Hull": self._apply_convex_hull,
        }
