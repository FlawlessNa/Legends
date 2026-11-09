"""
What a `FootholdGraph` holds and returns, in virtual px and seconds.

- A `MoveRange` is a move the graph stores: it works from every point of a
  stretch of its source surface, an x-range on a platform or a y-range on a
  rope. A move that works from one point only has `low == high`.
- A `Move` is one step of a `Path`, with an exact take-off and landing.

A surface is a `Platform` or a `Rope`, compared by value.
"""

from dataclasses import dataclass
from enum import StrEnum

from game_data.catalogue import Rope
from maple.model.world import Platform

type Surface = Platform | Rope
type Point = tuple[float, float]
"""A virtual position, `(x, y)`, y growing downwards."""


class MoveKind(StrEnum):
    """
    How the character gets from a take-off to a landing.

    - `WALK`: along a platform, or across a join onto another one.
    - `CLIMB`: along a rope or ladder, or between one and a platform that
      meets it (its top, or a platform crossing it).
    - `JUMP`: left, right or up from a platform, or left or right off a rope;
      it lands on a platform, or grabs a rope on the way.
    - `DROP`: down through the platform, onto the next one below.
    - `FALL`: off a platform's end (left or right), or off a rope's bottom
      (down).
    - `TELEPORT`: the teleport skill, left, right, up or down.
    - `PORTAL`: through a portal to another place on the same map.
    """

    WALK = "walk"
    CLIMB = "climb"
    JUMP = "jump"
    DROP = "drop"
    FALL = "fall"
    TELEPORT = "teleport"
    PORTAL = "portal"


class Direction(StrEnum):
    """Which way a move goes: the arrow key it is made with, where it has one."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class MoveRange:
    """
    A move that works from a stretch of its source surface.

    :ivar low: The stretch's start: an x on a platform, a y on a rope.
    :ivar high: Its end; `low <= high`.
    :ivar landing_low: Where the move from `low` lands, on `target`.
    :ivar landing_high: Where the move from `high` lands.
    :ivar duration_low: Seconds the move from `low` takes.
    :ivar duration_high: Likewise from `high`.
    """

    kind: MoveKind
    direction: Direction | None
    source: Surface
    target: Surface
    low: float
    high: float
    landing_low: Point
    landing_high: Point
    duration_low: float
    duration_high: float


@dataclass(frozen=True, slots=True)
class Move:
    """
    One step of a `Path`.

    :ivar start: The exact take-off, on `start_on`.
    :ivar end: The exact landing, on `end_on`.
    :ivar duration: Seconds it takes, from the physics; a portal or a teleport
        takes a fixed planning time (`foothold_graph`).
    """

    kind: MoveKind
    direction: Direction | None
    start: Point
    end: Point
    start_on: Surface
    end_on: Surface
    duration: float


@dataclass(frozen=True, slots=True)
class Path:
    """
    The moves from a start to a goal, in order: each starts where the one
    before it ends. A path from a point to itself has no moves.
    """

    moves: tuple[Move, ...]

    @property
    def duration(self) -> float:
        """Seconds the whole path takes."""
        return sum(m.duration for m in self.moves)
