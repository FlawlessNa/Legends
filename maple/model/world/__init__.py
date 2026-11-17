"""
The map model in virtual px, built from `game_data` (#302, Part 2).

- `WorldMap.load(map)`: a map's platforms, walls, ropes and ladders, portals,
  VR bounds and minimap transform, from the latest extraction's catalogue
  (`world_map`); a random point on its platforms, and the platform or rope at
  a point.
- `Platform` and `chain_platforms`: how footholds are chained into platforms,
  and which links count (`platforms`).
- `StaticRender`: the map's static layers, drawn once and cached under the
  gitignored `data/map_render/<build>/` (`static_render`).
- `FrontArt`: which of the map's pixels are drawn over a character on a given
  layer, from its tiles and objects (`front_art`).
- `HuntingArea`: a rectangle of a map and the `Stretch`es of its Platforms
  it holds, cut into `cells`; the saved areas, one file per map,
  `configs/hunting_areas/<map id>.json` (`hunting_area`).

This package imports `game_data`; `game_data` never imports it.
"""

from .front_art import FrontArt
from .hunting_area import (
    CELL,
    EmptyHuntingArea,
    HuntingArea,
    Stretch,
    UnknownHuntingArea,
    cells,
)
from .platforms import Platform, chain_platforms, is_wall
from .static_render import MAP_RENDERS, StaticRender, draw_static
from .world_map import SURFACE_TOLERANCE, MinimapTransform, WorldMap

__all__ = [
    "CELL",
    "MAP_RENDERS",
    "SURFACE_TOLERANCE",
    "EmptyHuntingArea",
    "FrontArt",
    "HuntingArea",
    "MinimapTransform",
    "Platform",
    "StaticRender",
    "Stretch",
    "UnknownHuntingArea",
    "WorldMap",
    "cells",
    "chain_platforms",
    "draw_static",
    "is_wall",
]
