import random

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Box:
    """
    Immutable class to be used to represent an in-game area, defined by left, top, right, bottom points.
    Box can be read (through an OCR).
    When offset = True, the box is considered to be an offset which should be added to another box, e.g. it represents coordinates relative to another box.
    config can be provided as a string. This config is used as parameter for the OCR to improve accuracy.
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
        """Ensures that boxes not interpreted as offsets to another boxes should have positive dimensions"""
        if not self.offset:
            assert (
                self.width >= 0
            ), f"Box initialized with negative Width. Left is {self.left} whereas right is {self.right}"
            assert (
                self.height >= 0
            ), f"Box initialized with negative Height. Top is {self.top} whereas bottom is {self.bottom}"

    def __add__(self, other):
        """
        Adding two boxes together simply adds all their coordinates together.
        If both boxes have a config argument which is different, raise a Value error.
        If both boxes have a name argument which is different, raise a Value error.
        Otherwise, the resulting box will have the name of the only box with a name (or both boxes' name if they have the same name), and a similar behavior for config.
        Adding two offset boxes together results in a new offset box. Adding a non-offset box to an offset box result in a non-offset box.
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
        Allows to access the Box's attributes as if it was a dictionary. such as box['left'] or box['right']
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

    def crop_client_img(self) -> tuple[slice]:
        raise NotImplementedError
