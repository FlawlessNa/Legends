import numpy as np
import random

from dataclasses import dataclass, field
from .screenshots import CLIENT_HORIZONTAL_MARGIN_PX, CLIENT_VERTICAL_MARGIN_PX


@dataclass(frozen=True)
class Box:
    """
    Immutable class to be used to represent an in-game area,
    defined by left, top, right, bottom points.
    Box are used to crop screenshots and/or numpy arrays representing an image.
    Text enclosed within a Box can be read using OCR.
    When offset = True, the box is considered an offset to be added to another box,
     e.g. it represents coordinates relative to another box.
    Config can be provided as a string, used for improved accuracy with the OCR.
    When a Box is randomized, a random point inside the box is returned.
    """

    left: int = field()
    right: int
    top: int
    bottom: int
    name: str | None = field(default=None, compare=False)
    offset: bool = field(default=False, compare=False, repr=False)
    config: str | None = field(default=None, compare=False, repr=False)

    def __post_init__(self):
        """
        Ensures that non-offset boxes have positive dimensions.
        """
        if not self.offset:
            assert (
                self.width >= 0
            ), f"Box initialized with negative Width. Left is {self.left} whereas right is {self.right}"
            assert (
                self.height >= 0
            ), f"Box initialized with negative Height. Top is {self.top} whereas bottom is {self.bottom}"

    def __add__(self, other):
        """
        Add two boxes together by adding all their coordinates together.
        If both boxes have a config argument which is different, raise a Value error.
        If both boxes have a name argument which is different, raise a Value error.
        Otherwise, the resulting box will have the name of the only box with a name
         (or both boxes' name if they have the same name).
        The same behavior apply for their config attribute.
        Adding two offset boxes together results in a new offset box.
        Adding a non-offset box to an offset box result in a non-offset box.
        """
        if not isinstance(other, Box):
            raise TypeError(
                f"Cannot add {self.__class__.__name__} to {other.__class__.__name__}"
            )
        if (self.config and other.config and self.config != other.config) or (
            self.name and other.name and self.name != other.name
        ):
            raise ValueError(
                f"Cannot add two boxes with different configs or names -- configs: {self.config} and {other.config}, names: {self.name} and {other.name}"
            )

        name = self.name if self.name else other.name
        config = self.config if self.config else other.config
        offset = self.offset and other.offset
        return Box(
            left=self.left + other.left,
            right=self.right + other.right,
            top=self.top + other.top,
            bottom=self.bottom + other.bottom,
            name=name,
            offset=offset,
            config=config,
        )

    def __getitem__(self, item):
        """
        Allows to access the Box's attributes as if it was a dictionary.
        """
        return getattr(self, item)

    def __contains__(self, point: tuple[float, float]) -> bool:
        """
        Allows to check if a point is inside the box using the 'in' keyword.
        :param point: tuple of coordinates to check, in the form of (x, y)
        :return: bool
        """
        x, y = point
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def xrange(self) -> tuple[int, int]:
        return self.left, self.right

    @property
    def yrange(self) -> tuple[int, int]:
        return self.top, self.bottom

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2

    def random(self) -> tuple[int, int]:
        """Returns a random point inside the box"""
        return random.randint(*self.xrange), random.randint(*self.yrange)

    def extract_client_img(self,
                           client_img: np.ndarray,
                           top_offset: int = 0,
                           bottom_offset: int = 0,
                           left_offset: int = 0,
                           right_offset: int = 0) -> np.ndarray:
        """
        Returns the slices to be used to crop a full-client image.
        """
        return client_img[
               self.top-CLIENT_VERTICAL_MARGIN_PX+top_offset:self.bottom-CLIENT_VERTICAL_MARGIN_PX+bottom_offset,
               self.left-CLIENT_HORIZONTAL_MARGIN_PX+left_offset:self.right-CLIENT_HORIZONTAL_MARGIN_PX+right_offset
               ].copy()
