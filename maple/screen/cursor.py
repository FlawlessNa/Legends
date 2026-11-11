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

_SAMPLES = 8
"""How many of a cursor's opaque pixels are checked, exactly, before it is
matched at a position. A match within tolerance is nearly exact, and matching
the 59 cursors everywhere over the chat's log took 0.6 s."""


def cursor_mask(
    pixels: NDArray[np.uint8],
    cursors: list[NDArray[np.uint8]],
    area: tuple[int, int, int, int],
    tolerance: float = 0.5,
) -> NDArray[np.bool_]:
    """
    The pixels of `area` (x, y, width, height) that a cursor of `cursors`
    (RGBA) is drawn over: every pixel of its sprite with any opacity, wherever
    the whole sprite is matched over the area, in part or whole.
    """
    x, y, width, height = area
    mask = np.zeros((height, width), dtype=bool)
    reach = max(max(rgba.shape[:2]) for rgba in cursors) if cursors else 0
    x0, y0 = max(x - reach, 0), max(y - reach, 0)
    crop = pixels[y0 : y + height + reach, x0 : x + width + reach]
    packed = _pack(crop)
    for rgba in cursors:
        h, w = rgba.shape[:2]
        drawn = rgba[:, :, 3] > 0
        for left, top in _found(crop, packed, rgba, tolerance):
            left, top = left + x0 - x, top + y0 - y
            rows = slice(max(top, 0), min(top + h, height))
            columns = slice(max(left, 0), min(left + w, width))
            if rows.start >= rows.stop or columns.start >= columns.stop:
                continue
            mask[rows, columns] |= drawn[
                rows.start - top : rows.stop - top,
                columns.start - left : columns.stop - left,
            ]
    return mask


def _found(
    pixels: NDArray[np.uint8],
    packed: NDArray[np.uint32],
    rgba: NDArray[np.uint8],
    tolerance: float,
) -> list[tuple[int, int]]:
    """Every top-left where `rgba` is matched in `pixels`: first the positions
    where `_SAMPLES` of its opaque pixels are drawn exactly, then `match` at
    each of those."""
    h, w = rgba.shape[:2]
    rows, columns = packed.shape
    if rows < h or columns < w:
        return []
    ys, xs = np.nonzero(rgba[:, :, 3] == 255)
    if len(ys) == 0:
        return []
    candidates = np.ones((rows - h + 1, columns - w + 1), dtype=bool)
    for i in np.unique(np.linspace(0, len(ys) - 1, _SAMPLES).astype(int)):
        sy, sx = int(ys[i]), int(xs[i])
        r, g, b = (int(v) for v in rgba[sy, sx, :3])
        window = packed[sy : sy + rows - h + 1, sx : sx + columns - w + 1]
        candidates &= window == ((b << 16) | (g << 8) | r)
        if not candidates.any():
            return []
    found: list[tuple[int, int]] = []
    for cy, cx in zip(*np.nonzero(candidates), strict=True):
        at = (int(cx), int(cy))
        hits = match(pixels, rgba, (at[0], at[1], w, h), tolerance)
        if any((hit.x, hit.y) == at for hit in hits):
            found.append(at)
    return found


def _pack(pixels: NDArray[np.uint8]) -> NDArray[np.uint32]:
    """Each BGR pixel as one integer, `b << 16 | g << 8 | r`, so that a colour
    is compared across an area in one pass."""
    wide = pixels.astype(np.uint32)
    packed = (wide[:, :, 0] << 16) | (wide[:, :, 1] << 8) | wide[:, :, 2]
    return packed.astype(np.uint32)
