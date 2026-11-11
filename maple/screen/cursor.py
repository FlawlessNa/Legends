"""
The game's mouse cursor, which the client draws over everything, the readers'
elements included: its sprites, and where it is drawn over an area.
"""

import numpy as np
from numpy.typing import NDArray

from botting.screen import match

_CURSOR_FRAMES = {
    0: "0",
    1: "01",
    2: "0123456",
    3: "012345",
    4: "01",
    5: "0123",
    6: "0123456",
    7: "0124",
    8: "0124",
    9: "0",
    10: "0",
    11: "0",
    12: "0",
    13: "01",
    14: "0",
    15: "01",
    16: "0123",
}
CURSOR_PATHS = tuple(
    f"UI/Basic.img/Cursor/{state}/{frame}"
    for state, frames in _CURSOR_FRAMES.items()
    for frame in frames
)
"""The game's mouse cursor, every state and frame of `UI/Basic.img/Cursor`."""


def cursor_mask(
    pixels: NDArray[np.uint8],
    cursors: list[NDArray[np.uint8]],
    area: tuple[int, int, int, int],
    tolerance: float = 0.5,
) -> NDArray[np.bool_]:
    """
    The pixels of `area` (x, y, width, height) that a cursor of `cursors`
    (RGBA) is drawn over: every pixel of its sprite with any opacity, wherever
    the sprite is matched across the area, in part or whole.
    """
    x, y, width, height = area
    mask = np.zeros((height, width), dtype=bool)
    for rgba in cursors:
        h, w = rgba.shape[:2]
        region = (x - w + 1, y - h + 1, width + w - 1, height + h - 1)
        drawn = rgba[:, :, 3] > 0
        for hit in match(pixels, rgba, region, tolerance):
            top, left = hit.y - y, hit.x - x
            rows = slice(max(top, 0), min(top + h, height))
            columns = slice(max(left, 0), min(left + w, width))
            mask[rows, columns] |= drawn[
                rows.start - top : rows.stop - top,
                columns.start - left : columns.stop - left,
            ]
    return mask
