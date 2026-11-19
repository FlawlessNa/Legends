"""
A Hunting Area: a rectangle of a map, in virtual px, and the stretches of the
map's Platforms it holds; and the saved areas, one tracked file per map.

`HuntingArea` knows no map, so building one never raises. Asking it for its
`stretches` on a map gives what it holds there, possibly nothing;
`require_stretches` refuses a rectangle that holds nothing.

**Stretches.** A Platform's height is a broken line along its x, so the part of
it inside the rectangle is the part whose x and whose height are both inside: a
Platform that crosses the rectangle's side gives the part inside, and a sloped
one gives each part whose height is inside, which may be several. A stretch's
`y_at` is its Platform's.

**Cells.** `cells` cuts the stretches into equal pieces of at most `CELL`. What
the rotation looks around and what is left to go for are counted in cells.

**Points on them.** `random_point` draws a point on stretches, as
`WorldMap.random_point` does on Platforms, and `on_stretches` says whether a
point is on one: every destination in the area is.

**The saved file.** `configs/hunting_areas/<map id>.json`, the map id in plain
decimal:

    {
      "map": "Victoria Road: Henesys Hunting Ground I",
      "areas": {
        "right_corner": {"left": 1210, "top": -340, "right": 2180, "bottom": 215}
      }
    }

`map` is for the reader only. Saving rewrites the whole file with its areas
sorted by name, so saving the same areas twice gives the same bytes.

This module reads no screen, and imports nothing from `maple.decision_makers`,
`maple.screen` or `botting`.
"""

import json
import math
import os
import random
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Final

from game_data.catalogue import Foothold

from .platforms import Platform
from .world_map import WorldMap

CELL: Final = 150
"""The widest a cell may be, in virtual px."""

HUNTING_AREAS: Final = Path(__file__).resolve().parents[3] / "configs" / "hunting_areas"
"""Where the saved areas are, one file per map: `<map id>.json`."""

NAME: Final = re.compile(r"[a-z0-9_]{1,24}")
"""A saved area's name, matched in full."""

_SIDES: Final = ("left", "top", "right", "bottom")

ON_STRETCH: Final = 0.5
"""Virtual px: how far from a stretch's height a point may be and be on it."""


class EmptyHuntingArea(ValueError):
    """A Hunting Area that holds no stretch of the map's Platforms."""


class UnknownHuntingArea(LookupError):
    """
    No saved area of that name for the map, or no saved area for it at all.

    :ivar names: The names the map's file has, sorted; empty with no file.
    """

    def __init__(self, message: str, names: tuple[str, ...]) -> None:
        super().__init__(message)
        self.names = names


@dataclass(frozen=True, slots=True)
class Stretch:
    """
    The part of a Platform inside a Hunting Area, in virtual px.

    :ivar platform: The Platform it is part of.
    :ivar left: Its leftmost x, inside the Platform's own extent.
    :ivar right: Its rightmost x; equal to `left` for a Platform that only
        touches the rectangle.
    """

    platform: Platform
    left: float
    right: float

    @property
    def middle(self) -> tuple[float, float]:
        """The point halfway along its x, on its Platform."""
        x = (self.left + self.right) / 2
        y = self.y_at(x)
        assert y is not None  # x is within the stretch
        return x, y

    def y_at(self, x: float) -> float | None:
        """Its Platform's height at `x`; `None` when `x` is not on it."""
        if not self.left <= x <= self.right:
            return None
        return self.platform.y_at(x)


@dataclass(frozen=True, slots=True)
class HuntingArea:
    """
    A rectangle of a map, in whole virtual px, edges inside it.

    :ivar left: Its leftmost x.
    :ivar top: Its highest y (y grows downwards).
    :ivar right: Its rightmost x.
    :ivar bottom: Its lowest y.
    :ivar name: The name it is saved under; `None` for one drawn and not saved.
    """

    left: int
    top: int
    right: int
    bottom: int
    name: str | None = None

    def contains(self, point: tuple[float, float]) -> bool:
        """Whether `point` is inside the rectangle, its edges included."""
        x, y = point
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def distance(self, point: tuple[float, float]) -> float:
        """How far `point` is from the rectangle, in virtual px; 0 inside it."""
        x, y = point
        dx = max(self.left - x, 0.0, x - self.right)
        dy = max(self.top - y, 0.0, y - self.bottom)
        return math.hypot(dx, dy)

    def stretches(
        self, world_map: WorldMap, among: Sequence[Platform] | None = None
    ) -> tuple[Stretch, ...]:
        """
        The parts of the map's Platforms inside the rectangle, in the map's
        Platform order then left to right; empty when it holds none.

        :param among: The Platforms to keep to; all the map's by default.
        """
        platforms = world_map.platforms if among is None else among
        return tuple(s for p in platforms for s in self._clip(p))

    def require_stretches(self, world_map: WorldMap) -> tuple[Stretch, ...]:
        """
        `stretches`, refusing none.

        :raises EmptyHuntingArea: The rectangle holds no stretch of the map's
            Platforms; it names the map and the rectangle.
        """
        found = self.stretches(world_map)
        if not found:
            raise EmptyHuntingArea(
                f"the Hunting Area {self._describe()} holds no Platform "
                f"of map {world_map.id}"
            )
        return found

    def _describe(self) -> str:
        label = "" if self.name is None else f"{self.name!r} "
        return (
            f"{label}(left {self.left}, top {self.top}, "
            f"right {self.right}, bottom {self.bottom})"
        )

    def _clip(self, platform: Platform) -> list[Stretch]:
        low = max(self.left, platform.left)
        high = min(self.right, platform.right)
        if low > high:
            return []
        if low == high:
            pieces = self._inside(platform, low, low)
        else:
            # Between two consecutive ends of its footholds, the Platform's
            # height is one straight line: the first foothold spanning it.
            ends = {x for f in platform.footholds for x in (f.x1, f.x2)}
            xs = [low, *sorted(x for x in ends if low < x < high), high]
            pieces = [
                piece for a, b in pairwise(xs) for piece in self._inside(platform, a, b)
            ]
        merged: list[tuple[float, float]] = []
        for a, b in pieces:
            if merged and merged[-1][1] == a:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        return [Stretch(platform, a, b) for a, b in merged]

    def _inside(
        self, platform: Platform, a: float, b: float
    ) -> list[tuple[float, float]]:
        """The part of `[a, b]` where the Platform's height is inside."""
        foothold = _spanning(platform, (a + b) / 2)
        if foothold is None:
            return []
        ya, yb = _height(foothold, a), _height(foothold, b)
        if ya == yb:
            return [(a, b)] if self.top <= ya <= self.bottom else []
        at_top = (self.top - ya) / (yb - ya)
        at_bottom = (self.bottom - ya) / (yb - ya)
        start = max(0.0, min(at_top, at_bottom))
        end = min(1.0, max(at_top, at_bottom))
        if start > end:
            return []
        return [
            (
                a if start == 0.0 else a + (b - a) * start,
                b if end == 1.0 else a + (b - a) * end,
            )
        ]


def cells(stretches: Iterable[Stretch]) -> tuple[Stretch, ...]:
    """
    The stretches cut into pieces of at most `CELL` virtual px, each stretch
    into as few equal pieces as that allows, in the order given.
    """
    found: list[Stretch] = []
    for s in stretches:
        width = s.right - s.left
        count = max(1, math.ceil(width / CELL))
        cuts = [s.left + width * i / count for i in range(count)] + [s.right]
        found.extend(Stretch(s.platform, a, b) for a, b in pairwise(cuts))
    return tuple(found)


def random_point(
    stretches: Sequence[Stretch], rng: random.Random | None = None
) -> tuple[float, float]:
    """
    A point on the stretches, drawn uniformly along their widths: a stretch is
    picked with a weight of its width, the point's x uniformly across it, and
    its y on it there. A stretch with no width (a Platform that only touches
    the rectangle) weighs one virtual px.

    :param rng: The generator to draw with; the `random` module's own by
        default.
    :raises ValueError: There is no stretch.
    """
    if not stretches:
        raise ValueError("no stretch to pick a point on")
    draw = rng or random
    (stretch,) = draw.choices(
        stretches, weights=[max(s.right - s.left, 1.0) for s in stretches]
    )
    x = draw.uniform(stretch.left, stretch.right)
    y = stretch.y_at(x)
    assert y is not None  # x is within the stretch
    return x, y


def on_stretches(point: tuple[float, float], stretches: Iterable[Stretch]) -> bool:
    """Whether `point` is on one of the stretches: within its x, at its height."""
    x, y = point
    for s in stretches:
        height = s.y_at(x)
        if height is not None and abs(height - y) <= ON_STRETCH:
            return True
    return False


# --- the saved file ------------------------------------------------------------


def area_file(map_id: int, folder: Path = HUNTING_AREAS) -> Path:
    """Where a map's saved areas are: `<folder>/<map id>.json`."""
    return folder / f"{map_id}.json"


def saved_areas(map_id: int, folder: Path = HUNTING_AREAS) -> dict[str, HuntingArea]:
    """The map's saved areas by name, sorted; empty when it has no file."""
    path = area_file(map_id, folder)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        name: HuntingArea(*(int(rect[side]) for side in _SIDES), name=name)
        for name, rect in sorted(data["areas"].items())
    }


def load_area(map_id: int, name: str, folder: Path = HUNTING_AREAS) -> HuntingArea:
    """
    The map's saved area of that name.

    :raises UnknownHuntingArea: The map's file has no such name, or there is no
        file; it lists the names there are.
    """
    areas = saved_areas(map_id, folder)
    if name not in areas:
        names = tuple(areas)
        there = ", ".join(names) if names else "none"
        raise UnknownHuntingArea(
            f"map {map_id} has no saved Hunting Area {name!r} "
            f"in {area_file(map_id, folder)}; saved: {there}",
            names,
        )
    return areas[name]


def save_area(
    world_map: WorldMap, area: HuntingArea, folder: Path = HUNTING_AREAS
) -> Path:
    """
    Save the area in its map's file, under its name, replacing an area of that
    name; the folder is made if it is missing.

    :returns: The file written.
    :raises ValueError: The area's name is not 1 to 24 characters of `a-z`,
        `0-9` and `_`, or it has none.
    """
    if area.name is None or NAME.fullmatch(area.name) is None:
        raise ValueError(
            f"a Hunting Area is saved under 1 to 24 characters of a-z, 0-9 and _, "
            f"not {area.name!r}"
        )
    areas = saved_areas(world_map.id, folder) | {area.name: area}
    path = area_file(world_map.id, folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = path.with_suffix(".json.tmp")
    written.write_text(_file_text(world_map, areas), encoding="utf-8", newline="\n")
    os.replace(written, path)
    return path


def _file_text(world_map: WorldMap, areas: dict[str, HuntingArea]) -> str:
    """The file's text, its areas sorted by name, one to a line."""
    entries = [
        f"    {json.dumps(name)}: "
        + json.dumps({side: getattr(area, side) for side in _SIDES})
        for name, area in sorted(areas.items())
    ]
    body = "{\n" + ",\n".join(entries) + "\n  }" if entries else "{}"
    label = json.dumps(_map_label(world_map), ensure_ascii=False)
    return f'{{\n  "map": {label},\n  "areas": {body}\n}}\n'


def _map_label(world_map: WorldMap) -> str:
    """Its street and name; the name alone with no street; else empty."""
    if world_map.name is None:
        return ""
    if world_map.street is None:
        return world_map.name
    return f"{world_map.street}: {world_map.name}"


def _spanning(platform: Platform, x: float) -> Foothold | None:
    """The first of its footholds spanning `x`, as `Platform.y_at` takes it."""
    for f in platform.footholds:
        if min(f.x1, f.x2) <= x <= max(f.x1, f.x2):
            return f
    return None


def _height(foothold: Foothold, x: float) -> float:
    """The foothold's line at `x`."""
    if x == foothold.x1:
        return float(foothold.y1)
    if x == foothold.x2:
        return float(foothold.y2)
    slope = (foothold.y2 - foothold.y1) / (foothold.x2 - foothold.x1)
    return foothold.y1 + slope * (x - foothold.x1)
