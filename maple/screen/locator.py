"""
Locating an on-screen element by its own sprites, and the frame check every
reader calls first.

An element is an anchor sprite plus its **fixed parts**: other opaque sprites
drawn at known positions relative to it. Each `Part` is placed the way the
client draws it, at a point given by a `vector:` node (or the element's own
point), with the sprite's origin on that point. So no position is measured off
a screen: it comes from origins and vectors.

`Locator.locate(frame)`:

1. re-checks the anchor where it was last found (one small match), and searches
   the frame only when it no longer matches there, or the frame's `client_size`
   changed;
2. when the anchor isn't found anywhere, searches for the fixed parts, so a
   covered anchor doesn't hide the element;
3. returns a `Located` saying which parts matched where expected, or `None`
   when neither the anchor nor any part was found.

`located_status` and `unreadable` turn that into `ABSENT`, `COVERED` or found.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading, Status, match_best, matches_at
from game_data.sprites import Sprite

from .sprites import GAUGE_LABEL, ReaderSprites

UI_NOT_FOUND = "UI not found at 1:1 (check UI Size)"


@dataclass(frozen=True, slots=True)
class Part:
    """
    A sprite drawn at `at`, relative to the element's point.

    :ivar sprite: The canvas, with its origin.
    :ivar at: Where the client draws it from the element's point: `(0, 0)` for
        the element's own canvas, or a `vector:` node for one placed by it.
    """

    sprite: Sprite
    at: tuple[int, int] = (0, 0)

    @property
    def offset(self) -> tuple[int, int]:
        """Its top-left corner, relative to the element's point."""
        return self.at[0] - self.sprite.origin[0], self.at[1] - self.sprite.origin[1]


@dataclass(frozen=True, slots=True)
class PartMatch:
    """
    Whether a part was found where the element's point puts it.

    :ivar path: The part's sprite path.
    :ivar x: Its expected top-left corner, in client pixels.
    :ivar y: Likewise.
    :ivar matched: Whether it matched there.
    """

    path: str
    x: int
    y: int
    matched: bool


@dataclass(frozen=True, slots=True)
class Located:
    """
    Where an element is, and which of its parts matched there.

    :ivar point: The element's point, in client pixels: where the client draws
        its anchor from. Add a `vector:` node to place a region by it.
    :ivar anchor: The anchor's match.
    :ivar parts: Each fixed part's match, in the `Locator`'s order.
    """

    point: tuple[int, int]
    anchor: PartMatch
    parts: tuple[PartMatch, ...]

    @property
    def complete(self) -> bool:
        """The anchor and every fixed part matched where expected."""
        return self.anchor.matched and all(part.matched for part in self.parts)

    def position(self, at: tuple[int, int]) -> tuple[int, int]:
        """A point given relative to the element's (a `vector:` node), in client pixels."""
        return self.point[0] + at[0], self.point[1] + at[1]


class Locator:
    """
    Finds one element, remembering where its anchor was.

    :ivar searches: How many `locate` calls had to search the frame, rather
        than find the anchor where it was last time.
    """

    def __init__(
        self, anchor: Part, parts: tuple[Part, ...] = (), tolerance: float = 0.5
    ) -> None:
        self.anchor = anchor
        self.parts = parts
        self.tolerance = tolerance
        self.searches = 0
        self._point: tuple[int, int] | None = None
        self._client_size: tuple[int, int] | None = None

    def locate(self, frame: Frame) -> Located | None:
        """The element in `frame`, or `None` when nothing of it is found."""
        pixels = frame.pixels
        if frame.client_size != self._client_size:
            self._client_size = frame.client_size
            self._point = None
        if self._point is not None and self._matches(pixels, self.anchor, self._point):
            return self._located(pixels, self._point)

        self.searches += 1
        self._point = None
        hit = match_best(pixels, self.anchor.sprite.rgba, tolerance=self.tolerance)
        if hit is not None:
            self._point = _point_of(self.anchor, hit.x, hit.y)
            return self._located(pixels, self._point)
        for part in self.parts:
            hit = match_best(pixels, part.sprite.rgba, tolerance=self.tolerance)
            if hit is not None:
                return self._located(pixels, _point_of(part, hit.x, hit.y))
        return None

    def _located(self, pixels: NDArray[np.uint8], point: tuple[int, int]) -> Located:
        return Located(
            point,
            self._part_match(pixels, self.anchor, point),
            tuple(self._part_match(pixels, part, point) for part in self.parts),
        )

    def _part_match(
        self, pixels: NDArray[np.uint8], part: Part, point: tuple[int, int]
    ) -> PartMatch:
        x, y = _top_left(part, point)
        return PartMatch(part.sprite.path, x, y, self._matches(pixels, part, point))

    def _matches(
        self, pixels: NDArray[np.uint8], part: Part, point: tuple[int, int]
    ) -> bool:
        x, y = _top_left(part, point)
        return matches_at(pixels, part.sprite.rgba, x, y, self.tolerance)


def _top_left(part: Part, point: tuple[int, int]) -> tuple[int, int]:
    dx, dy = part.offset
    return point[0] + dx, point[1] + dy


def _point_of(part: Part, x: int, y: int) -> tuple[int, int]:
    dx, dy = part.offset
    return x - dx, y - dy


def located_status(located: Located | None) -> Status:
    """`ABSENT` when nothing was found, `COVERED` when some parts didn't match
    where expected, `READ` when everything did."""
    if located is None:
        return Status.ABSENT
    return Status.READ if located.complete else Status.COVERED


# A reading that isn't READ carries no value, so it is a `Reading[T]` for every
# reader's `T`: the type parameter appears only in the return, on purpose.
def unreadable[T](located: Located | None, frame: Frame) -> Reading[T] | None:  # pyright: ignore[reportInvalidTypeVarUse]
    """
    The `ABSENT` or `COVERED` reading to return when the element can't be read,
    or `None` when it was found whole and can be.
    """
    match located_status(located):
        case Status.ABSENT:
            return Reading.absent(frame.captured_at, "not found")
        case Status.COVERED:
            assert located is not None
            missing = [
                part.path
                for part in (located.anchor, *located.parts)
                if not part.matched
            ]
            return Reading.covered(
                frame.captured_at, "not where expected: " + ", ".join(missing)
            )
        case _:
            return None


class FrameCheck:
    """
    Whether a frame can be read at all: it is `ok`, and the status bar's anchor
    is found at 1:1, which it isn't at a "UI Size" other than "Ideal Ratio".

    One per bot, shared by its readers; each calls `frame_usable` first. The
    answer for a frame is kept, so readers sharing a frame check it once.
    """

    def __init__(self, sprites: ReaderSprites) -> None:
        self.locator = Locator(Part(sprites.canvas(GAUGE_LABEL)))
        # Any: the readings kept are valueless, see `unreadable`.
        self._last: tuple[Frame, Reading[Any] | None] | None = None

    def frame_usable[T](self, frame: Frame) -> Reading[T] | None:  # pyright: ignore[reportInvalidTypeVarUse] - see `unreadable`
        """
        `None` when `frame` is usable; otherwise the `UNSURE` reading a reader
        returns for it.
        """
        if self._last is not None and self._last[0] is frame:
            return self._last[1]
        result = self._check(frame)
        self._last = (frame, result)
        return result

    def _check(self, frame: Frame) -> Reading[Any] | None:  # Any: see `unreadable`
        if not frame.ok:
            return Reading.unsure(
                frame.captured_at, f"frame not usable: {frame.reason}"
            )
        if self.locator.locate(frame) is None:
            return Reading.unsure(frame.captured_at, UI_NOT_FOUND)
        return None
