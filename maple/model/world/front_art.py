"""
The map's art drawn in front of a character: which pixels of the map hide a
character standing on a given layer (#517).

The client draws a map's layers 0 to 7 in turn, and a character, its name tag
included, with the layer of the foothold it stands on (a rope's or ladder's
`page` while it climbs): the tiles and objects of every layer above it are
drawn over it. At the top of Ellinia the ladder's top (`obj_connect.img`,
layer 2) is drawn over a character standing on the layer-1 platform beside
it, and hides about half of its name tag.

`FrontArt.covered(layer, box)` says, for each virtual pixel of a box, whether
a tile or an object of a layer above `layer` draws anything there (alpha above
0, so its soft edges count). An animated item counts with every frame's
pixels. Backgrounds are left out: a background marked `front` is drawn over
everything, but where depends on the camera (Ellinia has none).
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from game_data.catalogue import Catalogue, MapLayer
from game_data.config import STORE
from game_data.render import Images
from game_data.render.placement import top_left

type Mask = NDArray[np.bool_]
"""`(height, width)`, True where something is drawn."""


@dataclass(frozen=True, slots=True)
class _Piece:
    """One tile or object: where it is drawn, on which layer, and its pixels."""

    layer: int
    left: int
    top: int
    drawn: Mask

    @property
    def right(self) -> int:
        return self.left + self.drawn.shape[1]

    @property
    def bottom(self) -> int:
        return self.top + self.drawn.shape[0]


class FrontArt:
    """One map's tiles and objects, by layer, as masks of what they draw."""

    def __init__(self, pieces: Iterable[_Piece]) -> None:
        self._pieces = tuple(pieces)

    @classmethod
    def load(cls, build: str, map_id: int, root: Path = STORE) -> FrontArt:
        """
        A map's, from an extraction's catalogue and its image store.

        :raises CatalogueError: The store no longer has the extraction.
        :raises LookupError: As `Catalogue.map` does.
        :raises RenderError: The image store lacks an image the catalogue names.
        """
        with Catalogue.open(build, root) as cat:
            images = Images(cat.store.images)
            return cls.from_layers(cat.map_layers(map_id), images.get)

    @classmethod
    def from_layers(
        cls, items: Iterable[MapLayer], image: Callable[[str], NDArray[np.uint8]]
    ) -> FrontArt:
        """
        From a map's layer items, as `Catalogue.map_layers` gives them.

        :param image: An image's RGBA pixels, by its name in the image store.
        """
        return cls(
            piece
            for item in items
            if item.background is None and item.layer is not None
            if (piece := _piece(item, item.layer, image)) is not None
        )

    def covered(self, layer: int, box: tuple[int, int, int, int]) -> Mask:
        """
        Whether a tile or an object of a layer above `layer` draws on each
        virtual pixel of `box`, `(left, top, right, bottom)`, the right and
        bottom edges exclusive.
        """
        left, top, right, bottom = box
        mask = np.zeros((max(0, bottom - top), max(0, right - left)), np.bool_)
        for p in self._pieces:
            if p.layer <= layer:
                continue
            x0, y0 = max(left, p.left), max(top, p.top)
            x1, y1 = min(right, p.right), min(bottom, p.bottom)
            if x0 >= x1 or y0 >= y1:
                continue
            mask[y0 - top : y1 - top, x0 - left : x1 - left] |= p.drawn[
                y0 - p.top : y1 - p.top, x0 - p.left : x1 - p.left
            ]
        return mask


def _piece(
    item: MapLayer, layer: int, image: Callable[[str], NDArray[np.uint8]]
) -> _Piece | None:
    """Every frame of an item laid together; `None` when none has pixels."""
    placed: list[tuple[int, int, Mask]] = []
    for frame in item.frames:
        if frame.image is None:
            continue
        drawn = image(frame.image)[..., 3] > 0
        if item.flip:
            drawn = drawn[:, ::-1]
        x, y = top_left(
            item.x,
            item.y,
            (frame.origin_x, frame.origin_y),
            drawn.shape[1],
            item.flip,
        )
        placed.append((x, y, drawn))
    if not placed:
        return None
    left = min(x for x, _, _ in placed)
    top = min(y for _, y, _ in placed)
    right = max(x + d.shape[1] for x, _, d in placed)
    bottom = max(y + d.shape[0] for _, y, d in placed)
    union = np.zeros((bottom - top, right - left), np.bool_)
    for x, y, d in placed:
        union[y - top : y - top + d.shape[0], x - left : x - left + d.shape[1]] |= d
    return _Piece(layer, left, top, union)
