"""
The footholds and ropes drawn on objects and tiles, in virtual coordinates.

Ported from the retired v83 map parser, whose modules were
`_objects.py`, `_tiles.py`, `_footholds.py` and `_ladder_rope.py`, keeping
what holds for Classic:

- **Where they are.** An object's frame 0, and a tile's canvas, may carry a
  `foothold` convex: a polyline whose points are relative to the item's
  position. A point `(px, py)` of an item at `(x, y)` is at `(x + px, y + py)`.
- **Ropes and ladders.** An object's frame 0 may carry a `ladder` or `rope`
  convex instead: two points with one x, the top and bottom of a vertical line.
  One object in the client spells it `laddeer`.

What Classic adds, or the v83 module didn't do:

- A `foothold` may be a sub-property of convexes, one polyline each, rather
  than one convex.
- A few objects carry their `foothold` beside their frames, on the object
  itself, rather than on frame 0. Both places are read.
- A flipped object mirrors its points about its position: `(x - px, y + py)`.
- A polyline of n points is `n - 1` segments, one row each. It isn't closed.

One object in the client also carries a convex named `0` on its frame, beside
no `foothold`. Nothing says what it is, so a numbered convex is read as
neither. Any other convex on an object's frame or on a tile is an error: its
meaning would be a guess.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from .trees import Tree

FOOTHOLD: Final = "foothold"
ROPES: Final = frozenset({"ladder", "rope", "laddeer"})

type Point = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Segment:
    """One straight piece of a foothold, from `(x1, y1)` to `(x2, y2)`."""

    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True, slots=True)
class Climb:
    """A rope or ladder: the vertical line at `x` from `y1` to `y2`."""

    x: int
    y1: int
    y2: int


def segments(points: Sequence[Point]) -> list[Segment]:
    """The segments joining consecutive points: none for fewer than two."""
    return [Segment(x1, y1, x2, y2) for (x1, y1), (x2, y2) in pairwise(points)]


def placed(points: Iterable[Point], x: int, y: int, flip: bool) -> list[Point]:
    """Points relative to an item at `(x, y)`, in virtual coordinates."""
    return [(x - px if flip else x + px, y + py) for px, py in points]


def convex_points(node: Tree) -> list[Point]:
    """A convex's points, in order."""
    node.expect("convex")
    return [child.resolved().vector() for _, child in node.children()]


def polylines(foothold: Tree) -> list[list[Point]]:
    """A `foothold` child's polylines: one convex, or a sub-property of them."""
    node = foothold.resolved()
    if node.type == "convex":
        return [convex_points(node)]
    node.expect("property")
    return [convex_points(child.resolved()) for _, child in node.children()]


def footholds(holders: Iterable[Tree], x: int, y: int, flip: bool) -> list[Segment]:
    """
    The foothold segments an item carries, placed.

    :param holders: The nodes that may carry them: a tile's canvas, or an
        object's frame 0 and the object itself.
    """
    found: list[Segment] = []
    for holder in holders:
        _check_convexes(holder)
        foothold = holder.get(FOOTHOLD)
        if foothold is None:
            continue
        for line in polylines(foothold):
            found += segments(placed(line, x, y, flip))
    return found


def climbs(holders: Iterable[Tree], x: int, y: int, flip: bool) -> list[Climb]:
    """The ropes and ladders an object carries, placed."""
    found: list[Climb] = []
    for holder in holders:
        _check_convexes(holder)
        for name, child in holder.children():
            if name not in ROPES:
                continue
            node = child.resolved()
            points = placed(convex_points(node), x, y, flip)
            if len(points) != 2 or points[0][0] != points[1][0]:
                raise node.error(
                    f"a {name} should be two points with one x, not {points}"
                )
            (top_x, top), (_, bottom) = points
            found.append(Climb(top_x, top, bottom))
    return found


def _check_convexes(holder: Tree) -> None:
    for name, child in holder.children():
        known = name == FOOTHOLD or name in ROPES or name.isdigit()
        if child.type == "convex" and not known:
            raise child.error("a convex nobody knows the meaning of")
