"""
Where a map's tiles, objects and backgrounds go, in virtual coordinates, and in
what order they're drawn. Nothing here touches pixels.

Ported from the retired v83 map parser, whose modules were
`_objects.py`, `_tiles.py` and `map_parser.py`, keeping what holds for
Classic:

- **Origin.** An item at `(x, y)` puts its frame's `origin` there, so the
  frame's top left is at `(x - origin_x, y - origin_y)`.
- **Layers.** Layers are drawn from 0 to 7, each over the one before.

What the v83 module got wrong, or didn't do:

- **Flip.** It mirrored the pixels but kept the top left, so a flipped item
  moved by its width less twice its origin. A flipped item mirrors about its
  position, as its footholds do (`catalogue.geometry`): its top left is at
  `x - (width - origin_x)`.
- **Order within a layer.** It sorted tiles and objects together, an object's
  `z` against a tile's `zM`. The client draws a layer's objects first, by `z`,
  then its tiles, by their canvas's `z`, each in the map's order when equal.
  HaCreator's board does the same (read only, GPL; nothing is ported from it).
- **Frames.** Animated items are drawn at one frame, `frame % frame_count`.
- **Backgrounds,** which `_background.py` never read: those not in front are
  drawn before layer 0, and those in front after layer 7, each by number.
  Their parallax and tiling are `background_position` and `copies`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from game_data.catalogue import Background, Bounds, LayerFrame, MapLayer

STORED_AT_RX: Final = -100
"""
The `rx` (and `ry`) at which a background is drawn at its stored position in
virtual coordinates. A background's position moves with the camera's centre by
`(rx - STORED_AT_RX) / 100` of it (`background_position`).

-100 follows the client, as HaCreator reads it: a background with `rx = -100`
is fixed to the map, and one with `rx = 0` is fixed to the camera, as a sky
is, at its stored position from the camera's centre. Values in between are
parallax: the nearer -100, the more the background moves with the map.

The other reading is 0: a background with `rx = ry = 0` is drawn at its stored
position, and every other value moves it by `rx / 100` of the camera's centre.
That was the ticket's first wording (#267). The maintainer's visual check,
against the game, decides; to flip it, set this to 0.
"""

# A background's `type`: which ways it repeats. 4 to 7 also scroll over time,
# which a still render doesn't show.
_HORIZONTAL: Final = frozenset({1, 3, 4, 6, 7})
_VERTICAL: Final = frozenset({2, 3, 5, 6, 7})
TYPES: Final = range(8)


@dataclass(frozen=True, slots=True)
class Camera:
    """
    The camera the backgrounds are placed for: `width` by `height`, its top
    left at `(left, top)`, in virtual coordinates.
    """

    left: int
    top: int
    width: int
    height: int

    @classmethod
    def centred(cls, bounds: Bounds, viewport: tuple[int, int]) -> Camera:
        """A camera of the viewport's size, centred on the map's VR bounds."""
        width, height = viewport
        left = bounds.left + (bounds.right - bounds.left - width) // 2
        top = bounds.top + (bounds.bottom - bounds.top - height) // 2
        return cls(left, top, width, height)

    @property
    def centre(self) -> tuple[int, int]:
        return self.left + self.width // 2, self.top + self.height // 2


def frame_at(item: MapLayer, frame: int) -> LayerFrame | None:
    """The frame an item is drawn at, `frame % frame_count`; `None` for none."""
    if not item.frames:
        return None
    return item.frames[frame % len(item.frames)]


def top_left(
    x: int, y: int, origin: tuple[int, int], width: int, flip: bool
) -> tuple[int, int]:
    """
    Where a frame of `width` goes, its origin put at `(x, y)`: unflipped, its
    top left is `origin` up and left of it; flipped, it mirrors about `x`.
    """
    origin_x, origin_y = origin
    return (x - (width - origin_x) if flip else x - origin_x), y - origin_y


def draw_order(items: Iterable[MapLayer]) -> list[MapLayer]:
    """
    A map's tiles, objects and backgrounds, in the order they're drawn: the
    backgrounds behind, by number; then each layer, 0 to 7, its objects by
    `z` and then its tiles by `z`; then the backgrounds in front, by number.
    Equal keys keep the map's order.

    :raises ValueError: An item of a kind this doesn't know.
    """
    behind: list[MapLayer] = []
    layered: list[MapLayer] = []
    front: list[MapLayer] = []
    for item in items:
        if item.kind == "back":
            background = _background(item)
            (front if background.front else behind).append(item)
        elif item.kind in ("object", "tile"):
            layered.append(item)
        else:
            raise ValueError(f"a map layer of kind {item.kind!r}")
    layered.sort(key=lambda item: (item.layer, item.kind == "tile", item.z))
    return [
        *sorted(behind, key=lambda item: item.z),
        *layered,
        *sorted(front, key=lambda item: item.z),
    ]


def background_position(item: MapLayer, camera: Camera) -> tuple[int, int]:
    """
    Where a background's origin goes for `camera`, in virtual coordinates: its
    stored position, moved by `(rx - STORED_AT_RX) / 100` of the camera's
    centre, rounded down; likewise `ry` for y.
    """
    background = _background(item)
    centre_x, centre_y = camera.centre
    return (
        item.x + centre_x * (background.rx - STORED_AT_RX) // 100,
        item.y + centre_y * (background.ry - STORED_AT_RX) // 100,
    )


def copies(
    item: MapLayer, left: int, top: int, size: tuple[int, int], bounds: Bounds
) -> list[tuple[int, int]]:
    """
    Every top left a background's frame is drawn at: `(left, top)`, repeated
    every `cx` across the map's VR bounds if its type tiles horizontally, and
    every `cy` down them if vertically. A `cx` or `cy` of 0 or less is the
    frame's width or height. Copies that miss the bounds are left out.

    :param size: The frame's width and height.
    :raises ValueError: A background type this doesn't know.
    """
    background = _background(item)
    if background.type not in TYPES:
        raise ValueError(f"a background of type {background.type}")
    width, height = size
    xs = [left]
    if background.type in _HORIZONTAL:
        step = background.cx if background.cx > 0 else width
        xs = _repeats(left, width, step, bounds.left, bounds.right)
    ys = [top]
    if background.type in _VERTICAL:
        step = background.cy if background.cy > 0 else height
        ys = _repeats(top, height, step, bounds.top, bounds.bottom)
    return [(x, y) for y in ys for x in xs]


def _repeats(start: int, size: int, step: int, low: int, high: int) -> list[int]:
    """Each `start + k * step` whose `[at, at + size)` meets `[low, high)`."""
    if step <= 0 or size <= 0:
        return [start]
    first = (low - size - start) // step + 1
    last = -((start - high) // step) - 1
    return [start + k * step for k in range(first, last + 1)]


def _background(item: MapLayer) -> Background:
    if item.background is None:
        raise ValueError(f"a {item.kind} has no background properties")
    return item.background
