"""
`WorldMap`: one map's geometry, in virtual px, from `game_data`.

It holds the map's platforms and walls (`platforms`), its ropes and ladders,
its portals, its VR bounds, its minimap transform, and its static-layer render
(`static_render`). Everything is in virtual coordinates, the map's own, as the
game files store them; `WorldMap` names the map model, not a unit.

Only the map's own footholds and ropes are read. The footholds drawn on
objects and tiles have no `prev`/`next` to chain, and most of them lie exactly
on one of the map's own (796 of 1211 in Ellinia); the others are overlaps at
joins and templates, none a surface the map lacks. The ropes drawn on objects
each lie on one of the map's own, within 5 px (all 92 in Ellinia).
"""

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from game_data.catalogue import (
    Bounds,
    Catalogue,
    Foothold,
    MapData,
    Portal,
    Rope,
    Spawn,
)
from game_data.config import STORE

from .platforms import Platform, chain_platforms
from .static_render import MAP_RENDERS, StaticRender

SURFACE_TOLERANCE: Final = 16.0
"""How far a point may be from a platform or a rope to be on it, in virtual
px: one canvas pixel at `mag` 4, the coarse position's precision. The foothold
graph places a start or a goal within the same distance (`PLACE_TOLERANCE`)."""


@dataclass(frozen=True, slots=True)
class MinimapTransform:
    """
    How the minimap's canvas relates to virtual coordinates: the canvas is
    the map shifted by `centre`, then scaled down by `2**mag`.

    :ivar centre: Added to a virtual position to measure it from the canvas's
        top left (`miniMap/centerX`, `centerY`).
    :ivar mag: The canvas is scaled down by `2**mag` (16 for `mag` 4).
    """

    centre: tuple[int, int]
    mag: int

    @property
    def scale(self) -> int:
        """Virtual px per canvas px."""
        return 2**self.mag

    def to_virtual(self, canvas: tuple[float, float]) -> tuple[float, float]:
        """A canvas position, in virtual px: `canvas × scale − centre`."""
        return (
            canvas[0] * self.scale - self.centre[0],
            canvas[1] * self.scale - self.centre[1],
        )

    def to_canvas(self, virtual: tuple[float, float]) -> tuple[float, float]:
        """A virtual position, in canvas px: `(virtual + centre) ÷ scale`."""
        return (
            (virtual[0] + self.centre[0]) / self.scale,
            (virtual[1] + self.centre[1]) / self.scale,
        )


@dataclass(frozen=True, slots=True)
class WorldMap:
    """
    One map, in virtual px.

    :ivar id: The map's ID.
    :ivar name: Its name, without its street; `None` when the client names it
        nowhere, and so for `street`.
    :ivar bounds: Its VR bounds, the box the camera stays in.
    :ivar minimap: `None` when the map has no minimap.
    :ivar platforms: Its footholds chained into platforms (`platforms`).
    :ivar walls: Its vertical footholds, on no platform.
    :ivar ropes: Its own ropes and ladders (`source == "map"`), with `x`,
        `y1`, `y2`, `ladder` and `usable_from_foothold` as the catalogue gives
        them.
    :ivar portals: Its portals.
    :ivar static_render: Its static-layer render, cached per extraction;
        `None` for a map not loaded from a store.
    :ivar npcs: Its NPCs, where the map places them (`x`, and `cy`, the y of
        the foothold each stands on).
    """

    id: int
    name: str | None
    street: str | None
    bounds: Bounds
    minimap: MinimapTransform | None
    platforms: tuple[Platform, ...]
    walls: tuple[Foothold, ...]
    ropes: tuple[Rope, ...]
    portals: tuple[Portal, ...]
    static_render: StaticRender | None = None
    npcs: tuple[Spawn, ...] = ()

    @classmethod
    def load(
        cls, name_or_id: str | int, *, root: Path = STORE, cache: Path = MAP_RENDERS
    ) -> WorldMap:
        """
        A map from the latest extraction's catalogue. Its static render is
        drawn the first time it's asked for, not here.

        :param name_or_id: As `Catalogue.map` takes it.
        :param root: The game data store.
        :param cache: The folder static renders are cached under.
        :raises CatalogueError: The store has no extraction.
        :raises LookupError: As `Catalogue.map` does.
        """
        with Catalogue.latest(root) as cat:
            data = cat.map(name_or_id)
            build = cat.build
        return cls.from_map_data(data, StaticRender(build, data.id, root, cache))

    @classmethod
    def from_map_data(
        cls, data: MapData, static_render: StaticRender | None = None
    ) -> WorldMap:
        """A map from its `MapData`, as the catalogue gives it or built by hand."""
        platforms, walls = chain_platforms(
            f for f in data.footholds if f.source == "map"
        )
        minimap = None
        if data.minimap is not None:
            centre = (data.minimap.center_x, data.minimap.center_y)
            minimap = MinimapTransform(centre, data.minimap.mag)
        return cls(
            id=data.id,
            name=data.name,
            street=data.street,
            bounds=data.vr,
            minimap=minimap,
            platforms=platforms,
            walls=walls,
            ropes=tuple(r for r in data.ropes if r.source == "map"),
            portals=data.portals,
            static_render=static_render,
            npcs=tuple(s for s in data.spawns if s.kind == "npc"),
        )

    def random_point(
        self,
        among: Sequence[Platform] | None = None,
        rng: random.Random | None = None,
    ) -> tuple[float, float]:
        """
        A point on a platform, drawn uniformly along the platforms' widths: a
        platform is picked with a weight of its width (`right - left`), the
        point's x uniformly across it, and its y on the platform there. What
        a rotation with no feature cycle heads for (`NextTargetMixin`).

        :param among: The platforms to draw from; all the map's by default.
        :param rng: The generator to draw with; the `random` module's own by
            default.
        :raises ValueError: None of them has a width.
        """
        draw = rng or random
        platforms = self.platforms if among is None else tuple(among)
        widths = [p.right - p.left for p in platforms]
        if not any(w > 0 for w in widths):
            raise ValueError(f"map {self.id} has no platform to pick a point on")
        (platform,) = draw.choices(platforms, weights=widths)
        x = draw.uniform(platform.left, platform.right)
        y = platform.y_at(x)
        assert y is not None  # x is within the platform's own extent
        return x, y

    def platform_at(
        self, point: tuple[float, float], tolerance: float = SURFACE_TOLERANCE
    ) -> Platform | None:
        """
        The platform under `point`: of those spanning its x, the one whose
        height there is nearest its y, within `tolerance`. `None` when none
        is that close (the point in the air, or on a rope).
        """
        x, y = point
        best: tuple[float, Platform] | None = None
        for platform in self.platforms:
            height = platform.y_at(x)
            if height is None:
                continue
            distance = abs(height - y)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, platform)
        return None if best is None else best[1]

    def rope_at(
        self, point: tuple[float, float], tolerance: float = SURFACE_TOLERANCE
    ) -> Rope | None:
        """
        The rope or ladder nearest `point`, within `tolerance` of the line it
        hangs along; `None` when none is that close.
        """
        x, y = point
        best: tuple[float, Rope] | None = None
        for rope in self.ropes:
            top, bottom = min(rope.y1, rope.y2), max(rope.y1, rope.y2)
            distance = math.hypot(x - rope.x, y - min(max(y, top), bottom))
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, rope)
        return None if best is None else best[1]

    def layer_near(self, point: tuple[float, float], reach: float) -> int | None:
        """
        The lowest layer a character within `reach` of `point` could be drawn
        on: of the platforms passing within `reach` (in x and in y), their
        foothold layer, and of the ropes and ladders, their `page`. `None`
        when none is that close, or none says its layer.

        The lowest, because the art of every layer above a character's is
        drawn over it (`FrontArt`): taking a layer too low counts too much as
        hiding it, never too little.
        """
        x, y = point
        layers: list[int] = []
        for platform in self.platforms:
            nearest = min(max(x, platform.left), platform.right)
            height = platform.y_at(nearest)
            if (
                platform.layer is not None
                and height is not None
                and abs(nearest - x) <= reach
                and abs(height - y) <= reach
            ):
                layers.append(platform.layer)
        for rope in self.ropes:
            top, bottom = min(rope.y1, rope.y2), max(rope.y1, rope.y2)
            if (
                rope.page is not None
                and abs(rope.x - x) <= reach
                and top - reach <= y <= bottom + reach
            ):
                layers.append(rope.page)
        return min(layers, default=None)
