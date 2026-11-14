"""
Paths planned on a map's platforms and ropes, in virtual px (#302, Part 2).

- `FootholdGraph`: built from a `WorldMap` (`build`) or from any list of
  surfaces (`from_surfaces`); `path(start, goal)` runs A* (`foothold_graph`).
- `Path`, `Move`, `MoveRange`, `MoveKind`, `Direction`: what it holds and
  returns (`moves`).
- `Terrain`: where the character lands, traced along `VRPhysics`' arc
  (`terrain`).

- `FootholdGraphs`: a map's graphs, one per `VRPhysics`, built in a worker
  thread so a build never stalls the decision loop (`foothold_graphs`, #430).

Movement Plans are planned on it (`MovementHandler`, #396).
"""

from .foothold_graph import (
    DROP_REACH,
    JOIN_TOLERANCE,
    JUMP_RISE_SHARE,
    LANDING_MARGIN,
    PLACE_TOLERANCE,
    PORTAL_TIME,
    ROPE_GRAB_REACH,
    ROPE_TOP_SNAP,
    TELEPORT_TIME,
    FootholdGraph,
)
from .foothold_graphs import FootholdGraphs
from .moves import Direction, Move, MoveKind, MoveRange, Path, Point, Surface
from .terrain import Hits, Terrain

__all__ = [
    "DROP_REACH",
    "JOIN_TOLERANCE",
    "JUMP_RISE_SHARE",
    "LANDING_MARGIN",
    "PLACE_TOLERANCE",
    "PORTAL_TIME",
    "ROPE_GRAB_REACH",
    "ROPE_TOP_SNAP",
    "TELEPORT_TIME",
    "Direction",
    "FootholdGraph",
    "FootholdGraphs",
    "Hits",
    "Move",
    "MoveKind",
    "MoveRange",
    "Path",
    "Point",
    "Surface",
    "Terrain",
]
