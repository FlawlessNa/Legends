"""
`Terrain`: where the character lands, traced through a set of surfaces.

A surface is a platform or a rope; the terrain also holds the walls. It is
built from plain sequences, so surfaces from any source can be added: nothing
here assumes the platforms are a map's own, that they don't overlap, or that
the list is final.

Every trace is vectorised over many take-offs at once, in virtual px and
seconds, with virtual y growing downwards:

- `sweep`: a sideways arc (a jump, or a fall off an edge or a rope). The
  character lands on the first foothold it crosses **from above while
  descending**: footholds are passed through on the way up. A wall stops it:
  the arc is blocked when the feet cross a wall's x below its top and at or
  above its bottom, so a cliff face going down from an edge doesn't block a
  fall off that edge, and a wall rising from it does.
- `column`: the platforms straight above and below a take-off, for jumps up,
  drops, falls off a rope's bottom and teleports.

A surface's index is its place in `platforms`, then `ropes` after them.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from game_data.catalogue import Foothold, Rope
from maple.model.mechanics.physics import VRPhysics
from maple.model.world import Platform

type Floats = npt.NDArray[np.float64]
type Ints = npt.NDArray[np.int64]

#: Times at or below this are the take-off itself, never a landing.
_EPS = 1e-9
#: Heights within this are the same height (float noise on a foothold's line).
_TOL = 1e-6
#: Take-offs traced together; bounds the (take-offs × footholds) arrays.
_CHUNK = 256


@dataclass(frozen=True, slots=True)
class Hits:
    """
    What each traced take-off reached.

    :ivar surface: The surface's index; -1 for nothing (no landing, blocked
        by a wall, or out of reach).
    :ivar x: Where it landed or grabbed; NaN where `surface` is -1.
    :ivar y: Likewise.
    :ivar t: Seconds from take-off; NaN where `surface` is -1.
    """

    surface: Ints
    x: Floats
    y: Floats
    t: Floats


class Terrain:
    """
    The surfaces and walls the character moves through.

    :param platforms: Surfaces 0 to `len(platforms) - 1`.
    :param walls: Vertical footholds, which stop sideways arcs.
    :param ropes: Surfaces from `len(platforms)` on.
    :param physics: The arc, in virtual px and seconds.
    """

    def __init__(
        self,
        platforms: Sequence[Platform],
        walls: Sequence[Foothold],
        ropes: Sequence[Rope],
        physics: VRPhysics,
    ) -> None:
        self.platforms = tuple(platforms)
        self.ropes = tuple(ropes)
        self.physics = physics
        segments = [(i, f) for i, p in enumerate(self.platforms) for f in p.footholds]
        left = [min(f.x1, f.x2) for _, f in segments]
        right = [max(f.x1, f.x2) for _, f in segments]
        y_left = [f.y1 if f.x1 < f.x2 else f.y2 for _, f in segments]
        y_right = [f.y2 if f.x1 < f.x2 else f.y1 for _, f in segments]
        self._xa = np.array(left, dtype=float)
        self._xb = np.array(right, dtype=float)
        self._ya = np.array(y_left, dtype=float)
        self._slope = (np.array(y_right, dtype=float) - self._ya) / (
            self._xb - self._xa
        )
        self._fsurf = np.array([i for i, _ in segments], dtype=np.int64)
        self._wx = np.array([w.x1 for w in walls], dtype=float)
        self._wtop = np.array([min(w.y1, w.y2) for w in walls], dtype=float)
        self._wbot = np.array([max(w.y1, w.y2) for w in walls], dtype=float)
        self._rx = np.array([r.x for r in self.ropes], dtype=float)
        self._ry1 = np.array([min(r.y1, r.y2) for r in self.ropes], dtype=float)
        self._ry2 = np.array([max(r.y1, r.y2) for r in self.ropes], dtype=float)
        # The lowest foothold end: below it, an arc meets nothing.
        self._lowest = float(
            max(
                self._ya.max(initial=-np.inf),
                (self._ya + self._slope * (self._xb - self._xa)).max(initial=-np.inf),
            )
        )

    # --- the arc ---------------------------------------------------------------

    def arc_y(self, y0: Floats | float, vy0: float, t: Floats | float) -> Floats:
        """
        The feet's height `t` seconds after leaving `y0` at `vy0` (negative
        is upwards): under gravity until falling at `fall_speed`, then at it.
        """
        g, fs = self.physics.gravity, self.physics.fall_speed
        tc = (fs - vy0) / g
        t = np.asarray(t, dtype=float)
        rising = np.asarray(y0) + vy0 * t + g * t * t / 2
        capped = np.asarray(y0) + vy0 * tc + g * tc * tc / 2 + fs * (t - tc)
        return np.where(t <= tc, rising, capped)

    def descent_time(self, drop: float, vy0: float) -> float:
        """Seconds until the arc is `drop` below its start, on the way down."""
        g, fs = self.physics.gravity, self.physics.fall_speed
        tc = (fs - vy0) / g
        at_cap = vy0 * tc + g * tc * tc / 2
        if drop <= at_cap:
            return (-vy0 + np.sqrt(max(vy0 * vy0 + 2 * g * drop, 0.0))) / g
        return tc + (drop - at_cap) / fs

    # --- sideways --------------------------------------------------------------

    def sweep(
        self,
        x0: Floats,
        y0: Floats,
        vx: float,
        vy0: float,
        *,
        grab: bool = False,
    ) -> Hits:
        """
        Where sideways arcs from `(x0, y0)` land, at `vx` (non-zero) and
        `vy0`.

        :param grab: Report the first rope each arc crosses inside its height,
            before it lands or is blocked, instead of the landing; -1 where it
            crosses none.
        """
        n = len(x0)
        surface = np.full(n, -1, dtype=np.int64)
        hx = np.full(n, np.nan)
        hy = np.full(n, np.nan)
        ht = np.full(n, np.nan)
        for start in range(0, n, _CHUNK):
            part = slice(start, start + _CHUNK)
            s, x, y, t = self._sweep_chunk(x0[part], y0[part], vx, vy0, grab)
            surface[part], hx[part], hy[part], ht[part] = s, x, y, t
        return Hits(surface, hx, hy, ht)

    def _sweep_chunk(
        self, x0: Floats, y0: Floats, vx: float, vy0: float, grab: bool
    ) -> tuple[Ints, Floats, Floats, Floats]:
        g, fs = self.physics.gravity, self.physics.fall_speed
        n = len(x0)
        tc = (fs - vy0) / g
        apex = max(-vy0 / g, 0.0)
        t_min = max(apex, _EPS)
        # How far sideways any arc here can go before it is below every foothold.
        reach = abs(vx) * self.descent_time(
            max(self._lowest - float(y0.min()), 0.0) + 1.0, vy0
        )
        lo = float(x0.min()) - (reach if vx < 0 else 0.0)
        hi = float(x0.max()) + (reach if vx > 0 else 0.0)

        # Landings on footholds.
        keep = (self._xb >= lo) & (self._xa <= hi)
        xa, xb = self._xa[keep], self._xb[keep]
        ya, slope = self._ya[keep], self._slope[keep]
        fsurf = self._fsurf[keep]
        X0, Y0 = x0[:, None], y0[:, None]
        t1 = (xa - X0) / vx
        t2 = (xb - X0) / vx
        enter, leave = np.minimum(t1, t2), np.maximum(t1, t2)
        # Before the cap: g/2 t² + b t + c = 0, crossing downwards at the larger root.
        b = vy0 - slope * vx
        c = Y0 - ya - slope * (X0 - xa)
        disc = b * b - 2 * g * c
        with np.errstate(invalid="ignore"):
            root = (-b + np.sqrt(np.where(disc >= 0, disc, np.nan))) / g
        first = (root >= np.maximum(enter, t_min)) & (root <= np.minimum(leave, tc))
        # After the cap the arc is a line: it crosses downwards when it falls
        # faster than the foothold drops along it.
        k = fs - slope * vx
        at_cap = Y0 + vy0 * tc + g * tc * tc / 2 - ya - slope * (X0 + vx * tc - xa)
        with np.errstate(divide="ignore", invalid="ignore"):
            late = tc - at_cap / k
        second = (k > 0) & (late >= np.maximum(enter, max(tc, t_min))) & (late <= leave)
        t_hit = np.where(first, root, np.where(second, late, np.inf))
        if t_hit.shape[1]:
            best = np.argmin(t_hit, axis=1)
            t_land = t_hit[np.arange(n), best]
        else:
            best = np.zeros(n, dtype=np.int64)
            t_land = np.full(n, np.inf)

        # Walls in the way.
        t_block = np.full(n, np.inf)
        wkeep = (self._wx >= lo) & (self._wx <= hi)
        if wkeep.any():
            tw = (self._wx[wkeep] - X0) / vx
            yw = self.arc_y(Y0, vy0, tw)
            hit = (
                (tw > _EPS)
                & (yw > self._wtop[wkeep] + _TOL)
                & (yw <= self._wbot[wkeep] + _TOL)
            )
            t_block = np.where(hit, tw, np.inf).min(axis=1)

        if grab:
            t_grab = np.full(n, np.inf)
            which = np.zeros(n, dtype=np.int64)
            rkeep = np.flatnonzero((self._rx >= lo) & (self._rx <= hi))
            if len(rkeep):
                tr = (self._rx[rkeep] - X0) / vx
                yr = self.arc_y(Y0, vy0, tr)
                hit = (
                    (tr > _EPS)
                    & (yr >= self._ry1[rkeep] - _TOL)
                    & (yr <= self._ry2[rkeep] + _TOL)
                )
                tr = np.where(hit, tr, np.inf)
                pick = np.argmin(tr, axis=1)
                t_grab = tr[np.arange(n), pick]
                which = rkeep[pick]
            ok = np.isfinite(t_grab) & (t_grab < t_land) & (t_grab < t_block)
            surface = np.where(ok, len(self.platforms) + which, -1)
            gx = np.where(ok, self._rx[which] if len(self._rx) else np.nan, np.nan)
            gy = np.where(ok, self.arc_y(y0, vy0, np.where(ok, t_grab, 0.0)), np.nan)
            gy = (
                np.clip(gy, self._ry1[which], self._ry2[which]) if len(self._rx) else gy
            )
            return surface, gx, gy, np.where(ok, t_grab, np.nan)

        ok = np.isfinite(t_land) & (t_land < t_block)
        land_x = x0 + vx * np.where(ok, t_land, 0.0)
        land_y = ya[best] + slope[best] * (land_x - xa[best]) if len(xa) else land_x
        return (
            np.where(ok, fsurf[best] if len(xa) else -1, -1),
            np.where(ok, land_x, np.nan),
            np.where(ok, land_y, np.nan),
            np.where(ok, t_land, np.nan),
        )

    # --- straight up and down ---------------------------------------------------

    def column(self, x: Floats) -> tuple[Floats, Ints]:
        """
        The heights at each `x` of the footholds that span any of them, `inf`
        where one doesn't span that `x`, and the platform each is on: shapes
        `(len(x), footholds)` and `(footholds,)`.
        """
        keep = (self._xa <= float(x.max()) + _TOL) & (float(x.min()) - _TOL <= self._xb)
        xa, xb = self._xa[keep], self._xb[keep]
        X = x[:, None]
        spans = (xa <= X + _TOL) & (X - _TOL <= xb)
        heights = self._ya[keep] + self._slope[keep] * (np.clip(X, xa, xb) - xa)
        return np.where(spans, heights, np.inf), self._fsurf[keep]

    def nearest(
        self,
        x: Floats,
        above: Floats,
        below: Floats,
        *,
        exclude: Ints | int = -1,
        highest: bool = True,
    ) -> tuple[Ints, Floats]:
        """
        At each `x`, the platform whose height lies in `[above, below]`
        (inclusive), not `exclude`: the highest one, or the lowest.

        :returns: Each one's index, -1 for none, and its height there.
        """
        heights, owner = self.column(x)
        excluded = owner[None, :] == np.asarray(exclude).reshape(-1, 1)
        inside = (
            (heights >= np.asarray(above).reshape(-1, 1) - _TOL)
            & (heights <= np.asarray(below).reshape(-1, 1) + _TOL)
            & ~excluded
        )
        n = len(x)
        if not heights.shape[1]:
            return np.full(n, -1, dtype=np.int64), np.full(n, np.nan)
        if highest:
            pick = np.argmin(np.where(inside, heights, np.inf), axis=1)
        else:
            pick = np.argmax(np.where(inside, heights, -np.inf), axis=1)
        found = inside[np.arange(n), pick]
        return (
            np.where(found, owner[pick], -1),
            np.where(found, heights[np.arange(n), pick], np.nan),
        )

    # --- walls -----------------------------------------------------------------

    def wall_rises_at(self, x: float, y: float) -> bool:
        """A wall at `x` rises from `y`, or runs through it: an edge there is closed."""
        return bool(
            np.any(
                (np.abs(self._wx - x) <= _TOL)
                & (self._wtop < y - _TOL)
                & (y <= self._wbot + _TOL)
            )
        )

    def wall_between(self, x0: Floats, x1: Floats, y: Floats) -> npt.NDArray[np.bool_]:
        """Whether a wall stands between `x0` and `x1` (excluding `x0`) at feet `y`."""
        if not len(self._wx):
            return np.zeros(len(x0), dtype=bool)
        lo = np.minimum(x0, x1)[:, None]
        hi = np.maximum(x0, x1)[:, None]
        at_start = np.abs(self._wx - x0[:, None]) <= _TOL
        Y = y[:, None]
        return np.any(
            (self._wx >= lo - _TOL)
            & (self._wx <= hi + _TOL)
            & ~at_start
            & (Y > self._wtop + _TOL)
            & (Y <= self._wbot + _TOL),
            axis=1,
        )

    # --- surfaces --------------------------------------------------------------

    def platform_y(self, index: int, x: Floats) -> Floats:
        """A platform's height at each `x`, along the first foothold spanning it."""
        y = np.full(len(x), np.nan)
        for f in self.platforms[index].footholds:
            lo, hi = min(f.x1, f.x2), max(f.x1, f.x2)
            fill = np.isnan(y) & (x >= lo) & (x <= hi)
            y[fill] = f.y1 + (f.y2 - f.y1) * (x[fill] - f.x1) / (f.x2 - f.x1)
        return y
