"""
`WorldMap`: one map's geometry, in virtual px, from `game_data`.

It holds the map's platforms and walls (`platforms`), its ropes and ladders,
its portals, its VR bounds, its minimap transform, and its static-layer render
(`static_render`). Everything is in virtual coordinates, the map's own, as the
game files store them; `WorldMap` names the map model, not a unit.

Only the map's own footholds are read. The footholds drawn on objects and
tiles have no `prev`/`next` to chain, and most of them lie exactly on one of
the map's own (796 of 1211 in Ellinia).
"""

from dataclasses import dataclass
from pathlib import Path

from game_data.catalogue import Bounds, Catalogue, Foothold, MapData, Portal, Rope
from game_data.config import STORE

from .platforms import Platform, chain_platforms
from .static_render import MAP_RENDERS, StaticRender


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
    :ivar ropes: Its ropes and ladders, the map's own and those drawn on
        objects, with `x`, `y1`, `y2`, `ladder` and `usable_from_foothold` as
        the catalogue gives them.
    :ivar portals: Its portals.
    :ivar static_render: Its static-layer render, cached per extraction;
        `None` for a map not loaded from a store.
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
            ropes=data.ropes,
            portals=data.portals,
            static_render=static_render,
        )
