"""
Base classes for in-game visuals.
Contains methods for reading text, detecting colors or images in the game window.
"""

import cv2
import logging
import numpy as np
import os
import torch.cuda
import pytesseract
from abc import ABC, abstractmethod
from numpy import dtype, generic, ndarray
from typing import Any, Sequence
from ultralytics import YOLO
from ultralytics.engine.results import Results
from paths import ROOT
from botting.utilities import Box, take_screenshot, find_image


logger = logging.getLogger(__name__)


class InGameBaseVisuals(ABC):
    """
    Base class for in-game visuals.
    Should be used for any on-screen component that is "fixed" in game,
    meaning that it will always be in the same position.
    """

    @abstractmethod
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        For visuals that may contain characters, this method can be defined to preprocess
        the image before it is passed to pytesseract.
        Otherwise, it can be defined for enhancing detection of objects.
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
        Takes a screenshot of the provided region (box) in the window associated
        to the handle, and reads text from it.
        :param handle: The handle to the game client window.
        :param box: A box defining the on-screen area to read from.
        :param config: Any additional configuration for pytesseract, which may
         improve its accuracy. If not provided, box.config is used.
        :param confidence_level: The minimum confidence level for a character
         to be considered valid. Defaults to 15 (this is quite low).
        :return: string read by pytesseract.
        """
        img = take_screenshot(handle, box)
        if config is None:
            config = box.config
        return self.read_from_img(img, config, confidence_level)

    def read_from_img(
        self, image: np.ndarray, config: str | None = None, confidence_level: int = 15
    ) -> str:
        """
        Reads text from a pre-processed image by passing it into pytesseract.
        :param image: The raw image to read from.
        :param config: Any additional config for pytesseract, for improved accuracy.
        :param confidence_level: The minimum confidence level for a character
         to be considered valid. Defaults to 15 (this is quite low).
        :return:
        """
        img = self._preprocess_img(image)
        result = pytesseract.image_to_data(
            img, lang="eng", config=config or "", output_type=pytesseract.Output.DICT
        )
        filtered_res = [
            result["text"][i]
            for i in range(len(result["text"]))
            if int(result["conf"][i]) >= confidence_level
        ]
        return " ".join(filtered_res)

    @staticmethod
    def _color_detection(
        detection_img: np.ndarray,
        color: tuple[tuple, tuple],
        pixel_threshold: int = 0,
    ) -> bool:
        """
        Detects a color in an image.
        :param detection_img: Image in which to detect the color.
        :param color: Lower and upper bounds for the color to be detected.
        :param pixel_threshold: Amount of pixels that need to be detected for the
         color to be considered present. Defaults to 0.
        :return: Whether the color was detected or not, based on the pixel threshold.
        """
        detection_array = cv2.inRange(detection_img, *color)
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

    @staticmethod
    def _apply_contour_detection(
        image: np.ndarray, **kwargs
    ) -> Sequence[ndarray | ndarray[Any, dtype[generic | generic]] | Any]:
        contours, _ = cv2.findContours(image, **kwargs)
        return contours

    @staticmethod
    def _apply_bounding_rectangles(
        contours: Sequence[ndarray | ndarray[Any, dtype[generic | generic]] | Any],
        **kwargs,
    ) -> list[Sequence[int]]:
        return [cv2.boundingRect(cnt) for cnt in contours]

    @staticmethod
    def _apply_rectangle_grouping(
        rects: list[Sequence[int]], **kwargs
    ) -> Sequence[Sequence[int]]:
        return cv2.groupRectangles(rects, **kwargs)[0]

    @staticmethod
    def _apply_convex_hull(contour: Sequence[int], **kwargs) -> Sequence[int]:
        return cv2.convexHull(contour, **kwargs)

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


class InGameToggleableVisuals(InGameBaseVisuals, ABC):
    """
    Base class for in-game visuals that can be toggled on and off
     (usually through a key press or mouse click).
    """

    @abstractmethod
    def is_displayed(self, handle: int, image: np.ndarray = None) -> bool:
        """
        Checks whether the visual is currently displayed on screen.
        Must be implemented for each subclass.
        This can be done through color detection, image detection, or custom methods.
        :param handle: Handle to the game client.
        :param image: If provided, use this image.
        :return: Whether the visual is currently displayed on screen.
        Note that if the visual is obstructed (by cursor or other object),
         this method may fail.
        """
        pass


class InGameDynamicVisuals(InGameToggleableVisuals, ABC):
    """
    Base class for a visual that is dynamic, meaning it can be moved around the screen.
    Subclasses should define a needle image (saved in the assets/ folder)
     used for detection.
    The needle image can be only a small portion of the visual,
     as long as it is unique enough to be detected only once.
    The detection is made through templateMatching.
     If the visual is obstructed, it may not be properly detected.
    """

    _menu_icon_detection_needle: np.ndarray

    @classmethod
    def _menu_icon_position(
        cls, handle: int, client_img: np.ndarray | None = None
    ) -> Box | None:
        """
        Use the detection image to find the menu icon position.
        Child classes can use the result of this method to pinpoint the entire visual.
        :param handle: Handle to the game client.
        :param client_img: If provided, use this image.
        Otherwise, a screenshot of the entire client is taken.
        :return: Box coordinates of the menu icon.
        """
        if client_img is None:
            client_img = take_screenshot(handle)
        boxes = find_image(client_img, cls._menu_icon_detection_needle)
        if len(boxes) > 1:
            raise ValueError("More than one menu icon detected")
        elif boxes:
            return boxes.pop()

    def get_abs_box(
        self, handle: int, relative_box: Box, image: np.ndarray = None
    ) -> Box | None:
        """
        Returns the absolute box coordinates of the visual. The relative box is
        added to the menu icon position.
        :param handle:
        :param relative_box:
        :param image:
        :return:
        """
        if image is None:
            image = take_screenshot(handle)
        if self.is_displayed(handle, image):
            icon = self._menu_icon_position(handle, image)
            return icon + relative_box


class InGameDetectionVisuals(InGameBaseVisuals, ABC):
    """
    Base class for in-game objects for which a YOLO detection model may be used
    """
    _models: dict = {}
    detection_model: YOLO = None
    _prediction_cache: dict[int, Results] = {}
    _arg_cache: dict[int, int] = {}
    device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
    if device == torch.device('cpu'):
        logger.warning(
            "No CUDA device found. "
            "Using CPU for detection. Detections will be ~3x slower."
        )
    _model_cls_name: str = None
    DEFAULT_THRESHOLD = 0.65

    def __init__(self) -> None:
        self._set_model_for_cls()

    @staticmethod
    def register_cache_id(cache_id: int) -> None:
        """
        Register a cache_id for the prediction cache.
        """
        InGameDetectionVisuals._prediction_cache[cache_id] = None  # type: ignore
        InGameDetectionVisuals._arg_cache[cache_id] = None  # type: ignore

    @staticmethod
    def register_models(models_path: dict[str, str]) -> None:
        """
        Register models based on their path specifications, if not already registered.
        All models are registered to the base class InGameDetectionVisuals.
        """
        if models_path is None:
            return
        for class_, path in models_path.items():
            if class_ not in InGameDetectionVisuals._models:
                if not os.path.exists(path):
                    path = os.path.join(ROOT, path)
                assert os.path.exists(path), (
                    f"Model {path} does not exist."
                )
                model = YOLO(os.path.join(path, "weights/best.pt"), task="detect")
                InGameDetectionVisuals._models[class_] = model

    @classmethod
    def _set_model_for_cls(cls) -> None:
        """
        Returns the model path for the current class.
        """
        if cls.detection_model is None:
            model = cls._get_model_for_cls()
            if cls._is_detectable_by_model(model):
                cls.detection_model = model

    @classmethod
    def _get_model_for_cls(cls) -> YOLO | None:
        """
        Returns the model for the current class. If the class name is not in the
        registered models, look for the parent class recursively until found.
        If not found and "All" is in dictionary of models, then use that.
        Otherwise, return None.
        """
        if cls.__name__ in InGameDetectionVisuals._models:
            return InGameDetectionVisuals._models[cls.__name__]
        for parent in cls.__bases__:
            if issubclass(parent, InGameDetectionVisuals):
                return parent._get_model_for_cls()
        if "All" in InGameDetectionVisuals._models:
            return InGameDetectionVisuals._models["All"]

    @classmethod
    def _is_detectable_by_model(cls, model: YOLO) -> bool:
        """
        Returns whether the model is suitable for detection for the current class.
        """
        detectable_classes = model.names.values()  # type: ignore
        if cls.__name__ in detectable_classes:
            cls._model_cls_name = cls.__name__
            return True
        else:
            for parent in cls.__bases__:
                if issubclass(parent, InGameDetectionVisuals):
                    return parent._is_detectable_by_model(model)
        return False

    @classmethod
    def run_detection_model(
        cls,
        cache_id: int,
        image: np.ndarray,
        threshold: float = DEFAULT_THRESHOLD,
        debug: bool = False,
        mask: np.ndarray = None,
    ) -> Results:
        """
        Run the detection model on the image, and cache the result.
        # TODO - Consider debugging mode here with res.plot()
        # TODO - Try to reduce iou for less overlapping.
        """
        threshold = threshold or cls.DEFAULT_THRESHOLD
        hashed_args = hash((image.tobytes(), threshold))
        if InGameDetectionVisuals._arg_cache[cache_id] != hashed_args:
            res_list = cls.detection_model(
                image,
                conf=threshold,
                verbose=False,
                iou=0.3,
            )
            assert len(res_list) == 1, (
                f"Expected only one YOLO detection result, got {len(res_list)}."
            )
            InGameDetectionVisuals._prediction_cache[cache_id] = res_list.pop()
            InGameDetectionVisuals._arg_cache[cache_id] = hashed_args
        if debug:
            res = InGameDetectionVisuals._prediction_cache[cache_id].plot()
            if mask is not None:
                # Find contours in the mask
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
                thresh = cv2.threshold(mask, 0, 255, cv2.THRESH_BINARY)[1]
                contours, _ = cv2.findContours(
                    thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                if contours:
                    # Get the bounding box of the largest contour
                    x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
                    # Draw a rectangle on res using the bounding box coordinates
                    cv2.rectangle(res, (x, y), (x + w, y + h), (0, 0, 0), 2)

            cv2.imshow('Detection Model', res)
            cv2.waitKey(1)

        return InGameDetectionVisuals._prediction_cache[cache_id]

    @classmethod
    def extract_results(
        cls,
        res: Results,
        *,
        mask: np.ndarray,
        name: str = None,
    ) -> tuple[Sequence[int], ...]:
        """
        Extract the results from the YOLO detection model.
        When hide is provided, any results fully contained within any of the hide
        regions are removed.
        """
        if name is None:
            name = cls._model_cls_name
        vals = [
            tuple(map(round, dct['box'].values())) for dct in res.summary()
            if dct['name'] == name
        ]

        if mask is not None:
            assert mask.shape == res.orig_img.shape, (
                f"Mask shape {mask.shape} does not match image shape {res.orig_shape}."
            )
            # Remove any results if it is fully contained in a masked region
            # To do so, calculate the intersection of the result with the mask
            # if it is equal to the result, then it is fully contained in the mask
            intersection = cv2.bitwise_and(mask, res.orig_img)
            for pos in vals.copy():
                x1, y1, x2, y2 = pos
                if np.all(intersection[y1:y2, x1:x2] == 0):
                    vals.remove(pos)

        return tuple(vals)
