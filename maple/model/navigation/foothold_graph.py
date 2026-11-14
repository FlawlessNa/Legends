"""
`FootholdGraph`: paths planned on a map's own platforms and ropes, in
virtual px (#302, Part 2, P1).

**Built from plain lists.** `from_surfaces` takes the platforms, walls, ropes
and portal pairs the caller passes; `build` passes a `WorldMap`'s. Nothing
here reads map data or assumes the list is final: surfaces from another
source can be added to the lists, overlapping or not.

**Moves.** `moves` holds every move except travel along one surface (a walk
along a platform, a climb along a rope), each a `MoveRange`:

- `JUMP` left, right and up from every x of a platform, and left and right
  from every y of a rope (from the top of the arc, as the retired minimap grid
  did); each traced along `VRPhysics`' arc (`terrain`). A jump that lands back on
  its own platform is no move. A sideways jump may instead grab the first
  rope it crosses, and a jump up from right under a rope's bottom grabs it.
  A landing the character makes only with an exact take-off is no move
  either (#509): one on a platform higher than `JUMP_RISE_SHARE` of the arc,
  or a sideways jump's within `LANDING_MARGIN` of its platform's open end.
  Nor is a sideways jump off a platform that takes off within one input
  Step's walk of the open end it heads for (`TAKEOFF_STEP`, #515).
- `DROP` down through a platform, onto the next platform below within
  `DROP_REACH`.
- `FALL` off a platform's end, unless a wall rises there or another platform
  continues it (a join); and off a rope's bottom, straight down.
- `CLIMB` between a rope and a platform that meets it: one crossing it inside
  its height, or one at its top (within `ROPE_TOP_SNAP`) when the rope is
  `usable_from_foothold`.
- `WALK` across a join: a platform's end that lies on another platform
  continuing the same way.
- `PORTAL` from each portal pair's source to its target.
- `TELEPORT` (only with `teleport=True`) left, right, up and down, with
  the retired minimap grid's rules.

A move that works from a stretch is stored once, as an x-range (or a y-range
on a rope), split wherever its landing surface changes. Ranges are found by
tracing every whole virtual px of every surface, so they are exact to the px.

**Queries.** `path` places the start and the goal on their surfaces, inserts
them as temporary nodes, and runs A*. Nodes are the platforms' ends, the ropes'
ends, rope attachments, portals, and the ends and landings of every move.
Costs are seconds: the physics' for walks, climbs, jumps, drops and falls;
`PORTAL_TIME` and `TELEPORT_TIME` for the rest.

**Ties go to the walk.** `path` charges each `JUMP` `JUMP_TIE_PENALTY` more
than it takes, so a route with a jump is chosen only when it saves more than
that. Where the ground is flat a jump across a join costs exactly the walk's
time, and A* would otherwise plan it (#114). The jumps stay in `moves`, and a
`Move`'s duration is still the physics' own.

Movement Plans are planned on it (`MovementHandler`, #396), one graph per
`VRPhysics`, so a change of the character's stats builds a new one.
"""

import heapq
import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from itertools import pairwise
from typing import NamedTuple

import numpy as np

from botting.controller import TYPEMATIC_REPEAT
from game_data.catalogue import Foothold, Rope
from maple.model.mechanics.physics import VRPhysics
from maple.model.world import Platform, WorldMap

from .moves import Direction, Move, MoveKind, MoveRange, Path, Point, Surface
from .terrain import Floats, Ints, Terrain

#: How far below its take-off a drop may land, in virtual px. Today's grid
#: allows `JUMP_DOWN_LIMIT`, 30 minimap px; at 16 virtual px each that is 480.
#: Whether the client limits a drop at all is unverified: the physics Trial
#: schedule's drops (`configs/trials/physics.json`, #397) measure it live.
DROP_REACH = 480.0

#: How far above a rope's top a platform may lie and still meet it, in virtual
#: px. The files put a rope's top 2 to 3 px below the platform it climbs onto
#: (every rope of Ellinia and Damp Forest).
ROPE_TOP_SNAP = 4.0

#: How close a platform's end must lie to another platform to walk across, in
#: virtual px: the client's own joins coincide exactly.
JOIN_TOLERANCE = 1.0

#: How far a start, a goal or a portal may lie from the surface it is placed
#: on, in virtual px: one minimap px.
PLACE_TOLERANCE = 16.0

#: Seconds a portal is planned to take. Not in the game files: the retired
#: minimap grid charged a portal 1 minimap px of walking, 16 virtual px at
#: 125 px/s.
PORTAL_TIME = 16 / 125

#: Seconds a teleport is planned to take. Not in the game files: the retired
#: minimap grid charged a full-reach teleport (150 px, 9.375 minimap px)
#: 2 minimap px plus 40% of its length, as walking at 16 virtual px per minimap
#: px and 125 px/s.
TELEPORT_TIME = (2 + 0.4 * 150 / 16) * 16 / 125

#: The upward speed a jump off a rope starts with, in virtual px/s. The retired
#: grid started it at the top of the arc, with none; whether the client pushes
#: the character up is unverified: the physics Trial schedule's jumps off a
#: rope measure it live (#397). With none, a jump from one rope to
#: another always loses height.
ROPE_JUMP_SPEED = 0.0

_TOL = 1e-6

#: How high above its take-off a jump may land on a platform, as a share of
#: the arc's height (`VRPhysics.jump_height`); a take-off whose landing lies
#: higher is no move. The arc reaches its height at no speed, so a platform
#: there is met only exactly. Measured live (#509, Ellinia, Swordsman, speed
#: 100%, 2026-11-13): 40 jumps planned to land 77.0 px up, against an arc of
#: 77.006, and none landed there; the highest landing seen rose 73.6 px, its
#: airborne read on the traced arc to 2 px. 73.6 / 77.006 is 0.956: rounded down to the
#: hundredth, as a feasibility value is (`maple/calibration/analysis.py`).
JUMP_RISE_SHARE = 0.95

#: How far inside its landing platform a sideways jump must land, in virtual
#: px, from each end the character could go past: an end with no wall rising
#: at it and no platform continuing it. A take-off whose landing lies nearer is
#: no move. A jump's landing moves with its take-off, and the take-off is
#: where an open-loop walk stopped. Measured live (#509, the same runs):
#: jumps landing 0.4 to 8.6 px inside an open end landed 2 times in 13; those
#: landing 15.5 and 19.6 px inside landed 4 times in 5. So the narrowest
#: margin measured to land, not rounded: none between 8.6 and 15.5 was seen,
#: and a margin rounded down would plan landings no run has shown.
LANDING_MARGIN = 15.5

#: Seconds of walking a sideways jump off a platform must take off before the
#: open end it heads for: a take-off nearer that end is no move (#515). A jump
#: the character walks into takes off when its jump key goes down, and the
#: compile places that key no finer than one Step of the walk before it (a
#: walk's repeats are `TYPEMATIC_REPEAT` apart, and the last one can run that
#: far past the walk's time). So the take-off's margin is the walk speed times
#: this, in virtual px: 4.9 at the 149 px/s of the live runs. Live (#515,
#: Ellinia, 2026-11-14), a chained jump planned from a platform's open end
#: exactly, the one point it lands from, took off after the character had
#: walked off that end.
TAKEOFF_STEP = TYPEMATIC_REPEAT

#: Seconds `path` adds to a jump's cost when choosing between routes, so that
#: a tie goes to the walk. Under a frame (a 60 fps frame is 16.7 ms), and far
#: above the arc tracing's rounding.
JUMP_TIE_PENALTY = 1e-3


class _Edge(NamedTuple):
    to: int
    cost: float
    kind: MoveKind
    direction: Direction | None


type _Trace = Callable[[int, Floats], tuple[Ints, Floats, Floats, Floats]]
"""A move traced from surface `i` at coordinates `s`: target, x, y, seconds."""


class FootholdGraph:
    """
    A map's moves, and the paths through them. Build it with `build` or
    `from_surfaces`.

    :ivar moves: Every move but travel along one surface, in the order built.
    """

    def __init__(
        self,
        terrain: Terrain,
        portals: Sequence[tuple[Point, Point]],
        *,
        teleport: bool,
        drop_reach: float,
        rise_share: float = JUMP_RISE_SHARE,
        landing_margin: float = LANDING_MARGIN,
        takeoff_step: float = TAKEOFF_STEP,
    ) -> None:
        self._terrain = terrain
        self._physics = terrain.physics
        self._platforms = terrain.platforms
        self._ropes = terrain.ropes
        self._teleport = teleport
        self._drop_reach = drop_reach
        self._max_rise = rise_share * terrain.physics.jump_height
        self._landing_margin = landing_margin
        self._takeoff_margin = takeoff_step * terrain.physics.walk_speed
        self._surfaces: tuple[Surface, ...] = (*self._platforms, *self._ropes)
        ends = [self._open(i) for i in range(len(self._platforms))]
        self._open_left = np.array(
            [np.nan if a is None else a for a, _ in ends], dtype=float
        )
        self._open_right = np.array(
            [np.nan if b is None else b for _, b in ends], dtype=float
        )
        physics = terrain.physics
        teleport_rate = physics.teleport_reach / TELEPORT_TIME if teleport else 0.0
        self._vx_max = max(physics.walk_speed, teleport_rate)
        self._vy_max = max(
            physics.fall_speed, physics.jump_speed, physics.climb_speed, teleport_rate
        )

        # Each stored move's source and target index, and the trace that made it
        # (`None` for a move from one point), to trace it again from a start.
        self._records: list[tuple[MoveRange, int, int, _Trace | None]] = []
        self._build_moves(portals)
        self.moves = tuple(m for m, _, _, _ in self._records)
        self._ranges_from: dict[int, list[tuple[MoveRange, _Trace]]] = defaultdict(list)
        for move, source, _, trace in self._records:
            if trace is not None and move.low != move.high:
                self._ranges_from[source].append((move, trace))

        self._points: list[Point] = []
        self._owner: list[int] = []
        self._ids: dict[tuple[int, float], int] = {}
        self._edges: list[list[_Edge]] = []
        self._build_graph()

        self._portal_ends = [
            (self._point_at(source, m.low), m.landing_low)
            for m, source, _, _ in self._records
            if m.kind is MoveKind.PORTAL
        ]

    # --- building --------------------------------------------------------------

    @classmethod
    def build(
        cls, world_map: WorldMap, physics: VRPhysics, *, teleport: bool = False
    ) -> FootholdGraph:
        """
        The graph of a map's platforms, walls and ropes, and its portals that
        lead to another of its own portals.

        :param teleport: Add teleport moves, for a character that has the skill.
        """
        by_name = {p.name: p for p in world_map.portals}
        pairs = [
            ((p.x, p.y), (target.x, target.y))
            for p in world_map.portals
            if p.target_map == world_map.id
            and p.target_portal is not None
            and (target := by_name.get(p.target_portal)) is not None
            and target is not p
        ]
        return cls.from_surfaces(
            world_map.platforms,
            world_map.walls,
            world_map.ropes,
            physics,
            portals=pairs,
            teleport=teleport,
        )

    @classmethod
    def from_surfaces(
        cls,
        platforms: Sequence[Platform],
        walls: Sequence[Foothold],
        ropes: Sequence[Rope],
        physics: VRPhysics,
        *,
        portals: Iterable[tuple[Point, Point]] = (),
        teleport: bool = False,
        drop_reach: float = DROP_REACH,
        rise_share: float = JUMP_RISE_SHARE,
        landing_margin: float = LANDING_MARGIN,
        takeoff_step: float = TAKEOFF_STEP,
    ) -> FootholdGraph:
        """
        The graph of the surfaces given, from any source.

        :param walls: Vertical footholds; they stop sideways arcs.
        :param portals: `(source, target)` positions; each is placed on the
            surface under it, within `PLACE_TOLERANCE`, and a pair either end
            of which lies on no surface is left out.
        :param teleport: Add teleport moves.
        :param drop_reach: How far below its take-off a drop may land.
        :param rise_share: How high above its take-off a jump may land on a
            platform, as a share of the arc's height (`JUMP_RISE_SHARE`); 1
            takes the arc as traced.
        :param landing_margin: How far inside an open end of its landing
            platform a sideways jump must land (`LANDING_MARGIN`); 0 takes
            the arc as traced.
        :param takeoff_step: Seconds of walking a sideways jump off a platform
            must take off before the open end it heads for (`TAKEOFF_STEP`);
            0 takes every take-off as traced.
        """
        terrain = Terrain(platforms, walls, ropes, physics)
        return cls(
            terrain,
            tuple(portals),
            teleport=teleport,
            drop_reach=drop_reach,
            rise_share=rise_share,
            landing_margin=landing_margin,
            takeoff_step=takeoff_step,
        )

    def _build_moves(self, portals: Sequence[tuple[Point, Point]]) -> None:
        physics = self._physics
        walk = physics.walk_speed
        n_platforms = len(self._platforms)

        platform_traces: list[tuple[MoveKind, Direction, _Trace]] = [
            (MoveKind.JUMP, Direction.LEFT, self._jump_side(-walk, grab=False)),
            (MoveKind.JUMP, Direction.LEFT, self._jump_side(-walk, grab=True)),
            (MoveKind.JUMP, Direction.RIGHT, self._jump_side(walk, grab=False)),
            (MoveKind.JUMP, Direction.RIGHT, self._jump_side(walk, grab=True)),
            (MoveKind.JUMP, Direction.UP, self._jump_up),
            (MoveKind.DROP, Direction.DOWN, self._drop),
        ]
        if self._teleport:
            platform_traces += [
                (MoveKind.TELEPORT, Direction.LEFT, self._teleport_side(-1)),
                (MoveKind.TELEPORT, Direction.RIGHT, self._teleport_side(1)),
                (MoveKind.TELEPORT, Direction.UP, self._teleport_up),
                (MoveKind.TELEPORT, Direction.DOWN, self._teleport_down),
            ]
        rope_traces: list[tuple[MoveKind, Direction, _Trace]] = [
            (MoveKind.JUMP, Direction.LEFT, self._rope_jump(-walk, grab=False)),
            (MoveKind.JUMP, Direction.LEFT, self._rope_jump(-walk, grab=True)),
            (MoveKind.JUMP, Direction.RIGHT, self._rope_jump(walk, grab=False)),
            (MoveKind.JUMP, Direction.RIGHT, self._rope_jump(walk, grab=True)),
        ]

        for i, platform in enumerate(self._platforms):
            xs = _samples(platform.left, platform.right)
            for kind, direction, trace in platform_traces:
                self._add_runs(i, xs, kind, direction, trace)
            self._add_falls(i)
            self._add_joins(i)

        for j, rope in enumerate(self._ropes):
            i = n_platforms + j
            ys = _samples(min(rope.y1, rope.y2), max(rope.y1, rope.y2))
            for kind, direction, trace in rope_traces:
                self._add_runs(i, ys, kind, direction, trace)
            self._add_rope_ends(j)

        for source, target in portals:
            start = self.place(source)
            end = self.place(target)
            if start is None or end is None:
                continue
            self._point_move(
                MoveKind.PORTAL, None, start[0], start[1], end[0], end[2], PORTAL_TIME
            )

    def _add_runs(
        self,
        source: int,
        coords: Floats,
        kind: MoveKind,
        direction: Direction,
        trace: _Trace,
    ) -> None:
        """One `MoveRange` per run of consecutive samples landing on one surface."""
        target, x, y, t = trace(source, coords)
        target = np.where(target == source, -1, target)
        n = len(coords)
        start = 0
        while start < n:
            if target[start] < 0:
                start += 1
                continue
            end = start
            while end + 1 < n and target[end + 1] == target[start]:
                end += 1
            move = MoveRange(
                kind=kind,
                direction=direction,
                source=self._surfaces[source],
                target=self._surfaces[int(target[start])],
                low=float(coords[start]),
                high=float(coords[end]),
                landing_low=(float(x[start]), float(y[start])),
                landing_high=(float(x[end]), float(y[end])),
                duration_low=float(t[start]),
                duration_high=float(t[end]),
            )
            self._records.append((move, source, int(target[start]), trace))
            start = end + 1

    def _point_move(
        self,
        kind: MoveKind,
        direction: Direction | None,
        source: int,
        coord: float,
        target: int,
        landing: Point,
        duration: float,
    ) -> None:
        move = MoveRange(
            kind=kind,
            direction=direction,
            source=self._surfaces[source],
            target=self._surfaces[target],
            low=coord,
            high=coord,
            landing_low=landing,
            landing_high=landing,
            duration_low=duration,
            duration_high=duration,
        )
        self._records.append((move, source, target, None))

    # --- traces, each from surface `i` at coordinates `s` ----------------------

    def _jump_side(self, vx: float, *, grab: bool) -> _Trace:
        def trace(i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
            ys = self._terrain.platform_y(i, xs)
            hits = self._terrain.sweep(xs, ys, vx, -self._physics.jump_speed, grab=grab)
            surface = hits.surface.copy()
            platform = self._platforms[i]
            end = platform.right if vx > 0 else platform.left
            at_end = np.abs(xs - end) <= _TOL
            if at_end.any() and self._terrain.wall_rises_at(
                end, float(self._terrain.platform_y(i, np.array([end]))[0])
            ):
                surface[at_end] = -1
            # Too near the open end it heads for, the jump key can go down
            # after the character has walked off it (`TAKEOFF_STEP`).
            ahead = self._open_right[i] if vx > 0 else self._open_left[i]
            if not np.isnan(ahead):
                surface[np.abs(xs - ahead) < self._takeoff_margin - _TOL] = -1
            surface = self._sure_landings(surface, ys, hits.x, hits.y)
            return surface, hits.x, hits.y, hits.t

        return trace

    def _jump_up(self, i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
        ys = self._terrain.platform_y(i, xs)
        apex = ys - self._physics.jump_height
        # Falling back from the top, it lands on the first platform below it.
        surface, heights = self._terrain.nearest(xs, apex, ys, highest=True)
        # Too near the top, the landing is unsure: no move, not the next one
        # down, since the character may land on it still.
        surface = np.where(ys - heights > self._max_rise + _TOL, -1, surface)
        times = np.array(
            [
                self._physics.jump_landing_time(h - y) if s >= 0 else np.nan
                for s, h, y in zip(surface, heights, ys, strict=True)
            ]
        )
        return surface, np.where(surface >= 0, xs, np.nan), heights, times

    def _drop(self, i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
        ys = self._terrain.platform_y(i, xs)
        surface, heights = self._terrain.nearest(
            xs, ys + JOIN_TOLERANCE, ys + self._drop_reach, exclude=i, highest=True
        )
        times = np.array(
            [
                self._physics.fall_time(h - y) if s >= 0 else np.nan
                for s, h, y in zip(surface, heights, ys, strict=True)
            ]
        )
        return surface, np.where(surface >= 0, xs, np.nan), heights, times

    def _teleport_up(self, i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
        ys = self._terrain.platform_y(i, xs)
        reach = self._physics.teleport_reach
        surface, heights = self._terrain.nearest(
            xs, ys - reach, ys - JOIN_TOLERANCE, exclude=i, highest=True
        )
        return self._teleported(surface, xs, heights)

    def _teleport_down(self, i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
        ys = self._terrain.platform_y(i, xs)
        reach = self._physics.teleport_reach
        surface, heights = self._terrain.nearest(
            xs, ys + JOIN_TOLERANCE, ys + reach, exclude=i, highest=False
        )
        return self._teleported(surface, xs, heights)

    def _teleport_side(self, sign: int) -> _Trace:
        def trace(i: int, xs: Floats) -> tuple[Ints, Floats, Floats, Floats]:
            ys = self._terrain.platform_y(i, xs)
            reach = self._physics.teleport_reach
            to = xs + sign * reach
            # The nearest platform at or above the take-off's height, else the
            # nearest below, within half the reach: the retired grid's rule.
            up, up_y = self._terrain.nearest(to, ys - reach / 2, ys, highest=False)
            down, down_y = self._terrain.nearest(
                to, ys + _TOL, ys + reach / 2, highest=True
            )
            surface = np.where(up >= 0, up, down)
            heights = np.where(up >= 0, up_y, down_y)
            blocked = self._terrain.wall_between(xs, to, ys)
            surface = np.where(blocked, -1, surface)
            return self._teleported(surface, to, heights)

        return trace

    def _teleported(
        self, surface: Ints, xs: Floats, heights: Floats
    ) -> tuple[Ints, Floats, Floats, Floats]:
        found = surface >= 0
        return (
            surface,
            np.where(found, xs, np.nan),
            np.where(found, heights, np.nan),
            np.where(found, TELEPORT_TIME, np.nan),
        )

    def _rope_jump(self, vx: float, *, grab: bool) -> _Trace:
        def trace(i: int, ys: Floats) -> tuple[Ints, Floats, Floats, Floats]:
            rope = self._ropes[i - len(self._platforms)]
            xs = np.full(len(ys), float(rope.x))
            hits = self._terrain.sweep(xs, ys, vx, -ROPE_JUMP_SPEED, grab=grab)
            surface = self._sure_landings(hits.surface, ys, hits.x, hits.y)
            return surface, hits.x, hits.y, hits.t

        return trace

    def _sure_landings(self, surface: Ints, ys: Floats, x: Floats, y: Floats) -> Ints:
        """
        `surface`, with -1 for each sideways jump's landing on a platform that
        rises past `JUMP_RISE_SHARE` of the arc, or lies within
        `LANDING_MARGIN` of the platform's open end. A rope it grabs is kept.
        """
        if not self._platforms:
            return surface
        on_platform = (surface >= 0) & (surface < len(self._platforms))
        index = np.where(on_platform, surface, 0)
        margin = self._landing_margin - _TOL
        # NaN (a closed end) compares false: no margin is kept from it.
        with np.errstate(invalid="ignore"):
            unsure = (
                (ys - y > self._max_rise + _TOL)
                | (x - self._open_left[index] < margin)
                | (self._open_right[index] - x < margin)
            )
        return np.where(on_platform & unsure, -1, surface)

    def _open(self, i: int) -> tuple[float | None, float | None]:
        """
        Platform `i`'s left and right ends where the character can go past
        them, `None` for one a wall closes or another platform continues.
        """
        platform = self._platforms[i]
        ends: list[float | None] = []
        for end, direction in (
            (platform.left, Direction.LEFT),
            (platform.right, Direction.RIGHT),
        ):
            y = float(self._terrain.platform_y(i, np.array([float(end)]))[0])
            closed = self._terrain.wall_rises_at(end, y) or self._joins(
                i, end, y, direction
            )
            ends.append(None if closed else float(end))
        return ends[0], ends[1]

    # --- point moves -----------------------------------------------------------

    def _add_falls(self, i: int) -> None:
        """Off each end of platform `i`, unless a wall or a join closes it."""
        platform = self._platforms[i]
        walk = self._physics.walk_speed
        for end, vx, direction in (
            (platform.left, -walk, Direction.LEFT),
            (platform.right, walk, Direction.RIGHT),
        ):
            x = np.array([float(end)])
            y = self._terrain.platform_y(i, x)
            if self._terrain.wall_rises_at(end, float(y[0])) or self._joins(
                i, end, float(y[0]), direction
            ):
                continue
            hits = self._terrain.sweep(x, y, vx, 0.0)
            target = int(hits.surface[0])
            if target < 0 or target == i:
                continue
            self._point_move(
                MoveKind.FALL,
                direction,
                i,
                float(end),
                target,
                (float(hits.x[0]), float(hits.y[0])),
                float(hits.t[0]),
            )

    def _joins(
        self, i: int, x: float, y: float, direction: Direction
    ) -> list[tuple[int, float]]:
        """The other platforms platform `i`'s end at `(x, y)` walks onto."""
        heights, owner = self._terrain.column(np.array([x]))
        found: dict[int, float] = {}
        for k in np.flatnonzero(np.abs(heights[0] - y) <= JOIN_TOLERANCE):
            other = int(owner[k])
            target = self._platforms[other]
            onward = (
                target.right > x if direction is Direction.RIGHT else target.left < x
            )
            if other != i and onward and other not in found:
                found[other] = float(heights[0][k])
        return sorted(found.items())

    def _add_joins(self, i: int) -> None:
        platform = self._platforms[i]
        for end, direction in (
            (platform.left, Direction.LEFT),
            (platform.right, Direction.RIGHT),
        ):
            y = float(self._terrain.platform_y(i, np.array([float(end)]))[0])
            for other, height in self._joins(i, end, y, direction):
                self._point_move(
                    MoveKind.WALK,
                    direction,
                    i,
                    float(end),
                    other,
                    (float(end), height),
                    abs(height - y) / self._vy_max,
                )

    def _add_rope_ends(self, j: int) -> None:
        """Rope `j`'s attachments, its bottom's fall, and jumps up to grab it."""
        rope = self._ropes[j]
        i = len(self._platforms) + j
        top, bottom = min(rope.y1, rope.y2), max(rope.y1, rope.y2)
        x = float(rope.x)
        physics = self._physics
        heights, owner = self._terrain.column(np.array([x]))
        seen: set[tuple[int, float]] = set()
        for k in np.flatnonzero(np.isfinite(heights[0])):
            other, h = int(owner[k]), float(heights[0][k])
            if (other, round(h, 6)) in seen:
                continue
            seen.add((other, round(h, 6)))
            at_top = h <= top + ROPE_TOP_SNAP
            if top - ROPE_TOP_SNAP <= h <= bottom and not (
                at_top and rope.usable_from_foothold is False
            ):
                on = min(max(h, top), bottom)
                climb = abs(on - h) / physics.climb_speed
                # Onto the rope: down from a platform at its top, up elsewhere.
                self._point_move(
                    MoveKind.CLIMB,
                    Direction.DOWN if at_top else Direction.UP,
                    other,
                    x,
                    i,
                    (x, on),
                    climb,
                )
                self._point_move(
                    MoveKind.CLIMB,
                    Direction.UP if at_top else Direction.DOWN,
                    i,
                    on,
                    other,
                    (x, h),
                    climb,
                )
            elif bottom < h <= bottom + physics.jump_height:
                # From right under it, a jump up reaches its bottom.
                rise = h - bottom
                speed = physics.jump_speed
                t = (
                    speed - math.sqrt(max(speed**2 - 2 * physics.gravity * rise, 0.0))
                ) / (physics.gravity)
                self._point_move(
                    MoveKind.JUMP, Direction.UP, other, x, i, (x, float(bottom)), t
                )

        # Off its bottom, straight down onto the first platform below.
        surface, landed = self._terrain.nearest(
            np.array([x]), np.array([bottom + JOIN_TOLERANCE]), np.array([np.inf])
        )
        if surface[0] >= 0:
            drop = float(landed[0]) - bottom
            self._point_move(
                MoveKind.FALL,
                Direction.DOWN,
                i,
                float(bottom),
                int(surface[0]),
                (x, float(landed[0])),
                physics.fall_time(drop),
            )

    # --- the static graph -----------------------------------------------------

    def _node(self, surface: int, coord: float, point: Point | None = None) -> int:
        key = (surface, round(coord, 6))
        found = self._ids.get(key)
        if found is not None:
            return found
        self._ids[key] = len(self._points)
        self._points.append(
            point if point is not None else self._point_at(surface, coord)
        )
        self._owner.append(surface)
        self._edges.append([])
        return self._ids[key]

    def _point_at(self, surface: int, coord: float) -> Point:
        if surface < len(self._platforms):
            y = self._terrain.platform_y(surface, np.array([coord]))[0]
            return (coord, float(y))
        return (float(self._ropes[surface - len(self._platforms)].x), coord)

    def _coord(self, surface: int, point: Point) -> float:
        return point[0] if surface < len(self._platforms) else point[1]

    def _build_graph(self) -> None:
        for i, platform in enumerate(self._platforms):
            self._node(i, float(platform.left))
            self._node(i, float(platform.right))
        for j, rope in enumerate(self._ropes):
            i = len(self._platforms) + j
            self._node(i, float(min(rope.y1, rope.y2)))
            self._node(i, float(max(rope.y1, rope.y2)))
        for move, source, target, _ in self._records:
            for coord, landing, duration in (
                (move.low, move.landing_low, move.duration_low),
                (move.high, move.landing_high, move.duration_high),
            ):
                start = self._node(source, coord)
                end = self._node(target, self._coord(target, landing), landing)
                self._edges[start].append(
                    _Edge(end, duration, move.kind, move.direction)
                )
                if move.low == move.high:
                    break
        along: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for (surface, coord), node in self._ids.items():
            along[surface].append((coord, node))
        self._along: dict[int, tuple[list[float], list[int]]] = {}
        for surface, nodes in along.items():
            nodes.sort()
            self._along[surface] = ([c for c, _ in nodes], [n for _, n in nodes])
            for (_, a), (_, b) in pairwise(nodes):
                there, back = self._travel(
                    surface, a, self._points[a], b, self._points[b]
                )
                self._edges[a].append(there)
                self._edges[b].append(back)

    def _travel(
        self, surface: int, a: int, pa: Point, b: int, pb: Point
    ) -> tuple[_Edge, _Edge]:
        """A walk (on a platform) or a climb (on a rope) from `a` to `b`, and back."""
        on_rope = surface >= len(self._platforms)
        speed = self._physics.climb_speed if on_rope else self._physics.walk_speed
        along = abs(pb[1] - pa[1]) if on_rope else abs(pb[0] - pa[0])
        # Never below the lower bound A* uses, even along a steep slope.
        cost = max(along / speed, abs(pb[1] - pa[1]) / self._vy_max)
        if on_rope:
            kind, ahead, back = MoveKind.CLIMB, Direction.DOWN, Direction.UP
            forward = pb[1] > pa[1]
        else:
            kind, ahead, back = MoveKind.WALK, Direction.RIGHT, Direction.LEFT
            forward = pb[0] > pa[0]
        if not forward:
            ahead, back = back, ahead
        return _Edge(b, cost, kind, ahead), _Edge(a, cost, kind, back)

    # --- queries ---------------------------------------------------------------

    def place(
        self, point: Point, tolerance: float = PLACE_TOLERANCE
    ) -> tuple[int, float, Point] | None:
        """
        The surface nearest `point` within `tolerance`, a platform on a tie:
        its index, the coordinate along it, and the point on it. `None` when
        no surface is that close.
        """
        x, y = point
        best: tuple[float, int, float, Point] | None = None
        heights, owner = self._terrain.column(np.array([float(x)]))
        for k in np.flatnonzero(np.isfinite(heights[0])):
            distance = abs(float(heights[0][k]) - y)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (
                    distance,
                    int(owner[k]),
                    float(x),
                    (float(x), float(heights[0][k])),
                )
        for j, rope in enumerate(self._ropes):
            top, bottom = min(rope.y1, rope.y2), max(rope.y1, rope.y2)
            on = min(max(y, top), bottom)
            distance = math.hypot(x - rope.x, y - on)
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (
                    distance,
                    len(self._platforms) + j,
                    float(on),
                    (float(rope.x), float(on)),
                )
        if best is None:
            return None
        return best[1], best[2], best[3]

    def path(
        self, start: Point, goal: Point, *, tolerance: float = PLACE_TOLERANCE
    ) -> Path | None:
        """
        The quickest path from `start` to `goal`, each placed on the surface
        nearest it; `None` when no path joins them.

        :raises ValueError: `start` or `goal` lies on no surface within
            `tolerance`.
        """
        placed_start = self._place_or_raise("start", start, tolerance)
        placed_goal = self._place_or_raise("goal", goal, tolerance)
        query = _Query(self)
        s = query.add(*placed_start)
        g = query.add(*placed_goal)
        query.take_offs(s, placed_start[0], placed_start[1])
        query.link()
        return query.search(s, g)

    def reachable(
        self, start: Point, *, tolerance: float = PLACE_TOLERANCE
    ) -> tuple[Surface, ...]:
        """
        Every surface some path from `start` reaches, its own included, in
        the order given (platforms, then ropes).

        :raises ValueError: `start` lies on no surface within `tolerance`.
        """
        placed = self._place_or_raise("start", start, tolerance)
        query = _Query(self)
        first = query.add(*placed)
        query.link()
        seen = {first}
        stack = [first]
        while stack:
            for edge in query.neighbours(stack.pop()):
                if edge.to not in seen:
                    seen.add(edge.to)
                    stack.append(edge.to)
        found = {query.surface(node) for node in seen}
        return tuple(s for i, s in enumerate(self._surfaces) if i in found)

    def _place_or_raise(
        self, name: str, point: Point, tolerance: float
    ) -> tuple[int, float, Point]:
        placed = self.place(point, tolerance)
        if placed is None:
            raise ValueError(
                f"the {name} {point} lies on no platform or rope within "
                f"{tolerance} virtual px"
            )
        return placed

    def _lower_bound(self, a: Point, b: Point) -> float:
        return max(abs(a[0] - b[0]) / self._vx_max, abs(a[1] - b[1]) / self._vy_max)


class _Query:
    """One `path` query: the static graph, plus its temporary nodes."""

    def __init__(self, graph: FootholdGraph) -> None:
        self.graph = graph
        self.base = len(graph._points)
        self.points: list[Point] = []
        self.owner: list[int] = []
        self.edges: dict[int, list[_Edge]] = defaultdict(list)
        self.on: dict[int, list[tuple[float, int]]] = defaultdict(list)

    def add(self, surface: int, coord: float, point: Point) -> int:
        node = self.base + len(self.points)
        self.points.append(point)
        self.owner.append(surface)
        self.on[surface].append((coord, node))
        return node

    def point(self, node: int) -> Point:
        if node < self.base:
            return self.graph._points[node]
        return self.points[node - self.base]

    def surface(self, node: int) -> int:
        if node < self.base:
            return self.graph._owner[node]
        return self.owner[node - self.base]

    def take_offs(self, node: int, surface: int, coord: float) -> None:
        """The stored ranges that work from the start, traced from it exactly."""
        graph = self.graph
        for move, trace in graph._ranges_from.get(surface, ()):
            if not move.low - _TOL <= coord <= move.high + _TOL:
                continue
            target, x, y, t = trace(surface, np.array([coord]))
            to = int(target[0])
            if to < 0 or to == surface:
                continue
            landing = (float(x[0]), float(y[0]))
            end = self.add(to, graph._coord(to, landing), landing)
            self.edges[node].append(_Edge(end, float(t[0]), move.kind, move.direction))

    def link(self) -> None:
        """Each temporary node walks or climbs to its neighbours on its surface."""
        graph = self.graph
        for surface, temporary in self.on.items():
            coords, nodes = graph._along.get(surface, ([], []))
            merged = sorted([*zip(coords, nodes, strict=True), *temporary])
            temp = {n for _, n in temporary}
            for (_, a), (_, b) in pairwise(merged):
                if a in temp or b in temp:
                    there, back = graph._travel(
                        surface, a, self.point(a), b, self.point(b)
                    )
                    self.edges[a].append(there)
                    self.edges[b].append(back)

    def neighbours(self, node: int) -> Iterable[_Edge]:
        if node < self.base:
            yield from self.graph._edges[node]
        yield from self.edges.get(node, ())

    def heuristic(self, goal: Point) -> Callable[[int], float]:
        """
        A lower bound on the seconds from a node to `goal`, consistent: no
        move outruns the fastest speeds, and a path through portals pays at
        least one `PORTAL_TIME` and starts and ends its portal legs somewhere.
        """
        graph = self.graph
        gx, gy = goal
        per_x, per_y = 1 / graph._vx_max, 1 / graph._vy_max
        sources = [src for src, _ in graph._portal_ends]
        out = PORTAL_TIME + min(
            (graph._lower_bound(dst, goal) for _, dst in graph._portal_ends),
            default=math.inf,
        )
        known: dict[int, float] = {}

        def bound(node: int) -> float:
            found = known.get(node)
            if found is not None:
                return found
            x, y = self.point(node)
            value = max(abs(x - gx) * per_x, abs(y - gy) * per_y)
            for sx, sy in sources:
                value = min(value, max(abs(x - sx) * per_x, abs(y - sy) * per_y) + out)
            known[node] = value
            return value

        return bound

    def search(self, start: int, goal: int) -> Path | None:
        bound = self.heuristic(self.point(goal))
        best = {start: 0.0}
        came: dict[int, tuple[int, _Edge]] = {}
        done: set[int] = set()
        frontier = [(bound(start), 0.0, start)]
        static, base, extra = self.graph._edges, self.base, self.edges
        while frontier:
            _, cost, node = heapq.heappop(frontier)
            if node in done:
                continue
            if node == goal:
                return self._path(start, goal, came)
            done.add(node)
            edges = static[node] if node < base else ()
            for group in (edges, extra.get(node, ())):
                for edge in group:
                    to = edge.to
                    total = cost + edge.cost
                    if edge.kind is MoveKind.JUMP:
                        total += JUMP_TIE_PENALTY
                    if total < best.get(to, math.inf) and to not in done:
                        best[to] = total
                        came[to] = (node, edge)
                        heapq.heappush(frontier, (total + bound(to), total, to))
        return None

    def _path(self, start: int, goal: int, came: dict[int, tuple[int, _Edge]]) -> Path:
        graph = self.graph
        steps: list[tuple[int, int, _Edge]] = []
        node = goal
        while node != start:
            before, edge = came[node]
            steps.append((before, node, edge))
            node = before
        steps.reverse()
        moves: list[Move] = []
        for a, b, edge in steps:
            pa, pb = self.point(a), self.point(b)
            sa, sb = self.surface(a), self.surface(b)
            if sa == sb and pa == pb and edge.kind in (MoveKind.WALK, MoveKind.CLIMB):
                continue
            move = Move(
                kind=edge.kind,
                direction=edge.direction,
                start=pa,
                end=pb,
                start_on=graph._surfaces[sa],
                end_on=graph._surfaces[sb],
                duration=edge.cost,
            )
            last = moves[-1] if moves else None
            if (
                last is not None
                and move.kind in (MoveKind.WALK, MoveKind.CLIMB)
                and last.kind is move.kind
                and last.direction is move.direction
                and last.start_on == last.end_on == move.start_on == move.end_on
            ):
                moves[-1] = Move(
                    kind=last.kind,
                    direction=last.direction,
                    start=last.start,
                    end=move.end,
                    start_on=last.start_on,
                    end_on=move.end_on,
                    duration=last.duration + move.duration,
                )
            else:
                moves.append(move)
        return Path(tuple(moves))


def _samples(low: float, high: float) -> Floats:
    """Every whole virtual px from `low` to `high`, and both ends."""
    inner = np.arange(math.ceil(low), math.floor(high) + 1, dtype=float)
    return np.unique(np.concatenate([[float(low)], inner, [float(high)]]))
