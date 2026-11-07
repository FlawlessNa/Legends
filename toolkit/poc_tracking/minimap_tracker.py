"""
POC: track the character on the map's full minimap canvas, on any map.

**Capture only. This script never sends a key, a click or any other input to
the game.** It copies the client's pixels with Desktop Duplication (the same
`botting.screen.frame_source` the bot uses), or reads saved PNGs, and draws
what it finds in its own OpenCV window.

What it does, per frame:

1. Finds the expanded minimap by its own frame sprites (`UI/MiniMap.img`,
   `MaxMap` with the banner, or `MinMap` without): `nw`, then `ne` along its row
   and `sw` along its column, then `se` where both put it. The **map area** is
   the frame's inside. Its size is read, never assumed.
2. Places the map's own `miniMap/canvas` in the map area: the area is a window
   on the canvas, drawn 1:1, centred along an axis the canvas fits in and
   scrolled along one it doesn't. Every placement the area allows is scored by
   how many of the canvas's opaque (alpha 255) pixels are drawn exactly there;
   the last placement is tried first. A placement is trusted only when at least
   `MATCHED_SHARE` of the canvas's visible opaque pixels are drawn exactly and
   no other placement scores nearly as well.
3. Finds the character's marker (`Map/MapHelper.img/minimap/user`, origin on
   the character) and turns it into canvas pixels, then world pixels:
   `world = canvas * 2**mag - center` from the catalogue's `Minimap`.

Anything that can't be told reads **unsure**, with the reason; no position is
made up. Everything about the map comes from `game_data` (no map file).

Usage (from the repo root, with the venv's python)::

    python toolkit/poc_tracking/minimap_tracker.py --map Henesys
    python toolkit/poc_tracking/minimap_tracker.py --map auto
    python toolkit/poc_tracking/minimap_tracker.py --map auto --frames data/frames/v2
    python toolkit/poc_tracking/minimap_tracker.py --map auto --frames DIR \\
        --labels tests/frames/v2.json --headless       # accuracy only

Keys in the viewer: `q`/Esc quit, `c` clear the trail, `r` re-identify the
map (with `--map auto`); with `--frames`: space play/pause, `n`/`p` step.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import itertools

from botting.screen import match, matches_at
from game_data.catalogue import Catalogue
from game_data.sprites.sprites import Sprite, SpriteNotFound, Sprites

MINIMAP_IMG = "UI/MiniMap.img"
USER = "Map/MapHelper.img/minimap/user"

MATCHED_SHARE = 0.6
"""At least this share of the canvas's visible opaque pixels drawn exactly
places it (PR #365 saw 74% to 98% on a map's own canvas, 1% on another's)."""
AMBIGUOUS = 0.9
"""A placement whose runner-up (3+ px away) scores this close is unsure: the
canvas repeats itself, and either could be right."""
MIN_VISIBLE = 80
"""Fewer opaque canvas pixels than this in view can't place the canvas."""
SAMPLE = 400
"""Opaque canvas pixels compared at every placement during a search."""
TOLERANCE = 0.5
"""Mean squared error per opaque pixel for the frame pieces and the marker."""


def canvas_path(map_id: int) -> str:
    return f"Map/Map/Map{map_id // 100_000_000}/{map_id:09d}.img/miniMap/canvas"


def default_store() -> Path:
    """The repo's `data/game_data`; pass --store for another store."""
    return REPO / "data" / "game_data"


# ── The map, from game_data ─────────────────────────────────────────────────


@dataclass(frozen=True)
class MapInfo:
    id: int
    label: str
    canvas: Sprite
    center: tuple[int, int]
    scale: int  # 2**mag
    # Derived once: the canvas's opaque pixels, their BGR colours.
    ys: np.ndarray = field(repr=False)
    xs: np.ndarray = field(repr=False)
    colours: np.ndarray = field(repr=False)

    @property
    def size(self) -> tuple[int, int]:
        h, w = self.canvas.rgba.shape[:2]
        return w, h

    def world(self, at: tuple[int, int]) -> tuple[int, int]:
        return (
            at[0] * self.scale - self.center[0],
            at[1] * self.scale - self.center[1],
        )


class GameData:
    """The catalogue and the sprites, open for the whole run."""

    def __init__(self, root: Path) -> None:
        self.catalogue = Catalogue.latest(root)
        self.sprites = Sprites.latest(root)
        self._maps: dict[int, MapInfo | None] = {}

    def close(self) -> None:
        self.catalogue.close()
        self.sprites.close()

    def map(self, name_or_id: str | int) -> MapInfo:
        """:raises LookupError: no such map, or it has no minimap canvas."""
        data = self.catalogue.map(name_or_id)
        info = self.map_by_id(data.id)
        if info is None:
            raise LookupError(f"map {data.id} has no minimap canvas")
        return info

    def map_by_id(self, map_id: int) -> MapInfo | None:
        if map_id in self._maps:
            return self._maps[map_id]
        info = None
        data = self.catalogue.map(map_id)
        if data.minimap is not None:
            try:
                canvas = self.sprites.canvas(canvas_path(map_id))
            except SpriteNotFound:
                canvas = None
            if canvas is not None:
                ys, xs = np.nonzero(canvas.rgba[:, :, 3] == 255)
                if len(ys) >= MIN_VISIBLE:
                    label = f"{data.street or '?'}: {data.name or '?'} ({map_id})"
                    info = MapInfo(
                        map_id,
                        label,
                        canvas,
                        (data.minimap.center_x, data.minimap.center_y),
                        2**data.minimap.mag,
                        ys,
                        xs,
                        np.ascontiguousarray(canvas.rgba[ys, xs, 2::-1]),
                    )
        self._maps[map_id] = info
        return info

    def all_maps(self) -> list[MapInfo]:
        found = []
        for map_id in self.catalogue.ids("map"):
            info = self.map_by_id(map_id)
            if info is not None:
                found.append(info)
        return found


# ── Locating the minimap frame ──────────────────────────────────────────────


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Located:
    look: str  # "MaxMap", "MinMap" or "Min"
    bounds: Box  # the whole minimap, frame included
    area: Box | None  # the map area; None when minimised


class _Look:
    """One expanded look: `nw` with its fixed `n` and `w`, then `ne`, `sw`, `se`."""

    def __init__(self, sprites: Sprites, node: str) -> None:
        self.node = node
        p = {
            k: sprites.canvas(f"{MINIMAP_IMG}/{node}/{k}").rgba
            for k in ("nw", "n", "ne", "w", "sw", "se")
        }
        self.nw, self.n, self.ne, self.w, self.sw, self.se = (
            p[k] for k in ("nw", "n", "ne", "w", "sw", "se")
        )
        self.border = self.nw.shape[1]
        self.band = self.nw.shape[0]
        self.last: tuple[int, int, int, int] | None = None  # nw x, y; ne x; sw y

    def _box(self, x: int, y: int, ne_x: int, sw_y: int) -> Located:
        se_h, se_w = self.se.shape[:2]
        return Located(
            self.node,
            Box(x, y, ne_x + se_w - x, sw_y + se_h - y),
            Box(
                x + self.border,
                y + self.band,
                ne_x - x - self.border,
                sw_y - y - self.band,
            ),
        )

    def at_last(self, px: np.ndarray) -> Located | None:
        if self.last is None:
            return None
        x, y, ne_x, sw_y = self.last
        if (
            matches_at(px, self.nw, x, y, TOLERANCE)
            and matches_at(px, self.ne, ne_x, y, TOLERANCE)
            and matches_at(px, self.sw, x, sw_y, TOLERANCE)
            and matches_at(px, self.se, ne_x, sw_y, TOLERANCE)
        ):
            return self._box(x, y, ne_x, sw_y)
        return None

    def search(self, px: np.ndarray) -> Located | None:
        H, W = px.shape[:2]
        for hit in sorted(match(px, self.nw, None, TOLERANCE), key=lambda h: h.error):
            x, y = hit.x, hit.y
            if not (
                matches_at(px, self.n, x + self.border, y, TOLERANCE)
                and matches_at(px, self.w, x, y + self.band, TOLERANCE)
            ):
                continue
            nes = match(
                px,
                self.ne,
                (x + self.border, y, W - x - self.border, self.ne.shape[0]),
                TOLERANCE,
            )
            sws = match(
                px,
                self.sw,
                (x, y + self.band, self.sw.shape[1], H - y - self.band),
                TOLERANCE,
            )
            for ne in sorted(nes, key=lambda h: h.x):
                for sw in sorted(sws, key=lambda h: h.y):
                    if matches_at(px, self.se, ne.x, sw.y, TOLERANCE):
                        self.last = (x, y, ne.x, sw.y)
                        return self._box(x, y, ne.x, sw.y)
        return None


class FrameFinder:
    """Finds the minimap; where it was last time is checked first."""

    def __init__(self, sprites: Sprites) -> None:
        self.looks = [_Look(sprites, "MaxMap"), _Look(sprites, "MinMap")]
        self.min_w = sprites.canvas(f"{MINIMAP_IMG}/Min/w").rgba
        self.min_e = sprites.canvas(f"{MINIMAP_IMG}/Min/e").rgba

    def find(self, px: np.ndarray) -> Located | None:
        for look in self.looks:
            found = look.at_last(px)
            if found is not None:
                return found
        for look in self.looks:
            found = look.search(px)
            if found is not None:
                return found
        return self._minimised(px)

    def _minimised(self, px: np.ndarray) -> Located | None:
        _H, W = px.shape[:2]
        h, w = self.min_w.shape[:2]
        for hit in match(px, self.min_w, None, TOLERANCE):
            es = match(px, self.min_e, (hit.x + w, hit.y, W - hit.x - w, h), TOLERANCE)
            if es:
                e = min(es, key=lambda e: e.x)
                return Located(
                    "Min", Box(hit.x, hit.y, e.x + self.min_e.shape[1] - hit.x, h), None
                )
        return None


# ── Placing the canvas in the map area ──────────────────────────────────────


def _offsets(area: int, length: int) -> np.ndarray:
    """The canvas's possible top-left offsets along one axis: inside the area
    where it fits, a window on it (it scrolls) where it is longer."""
    if length <= area:
        return np.arange(0, area - length + 1)
    return np.arange(area - length, 1)


@dataclass(frozen=True)
class Placement:
    offset: tuple[int, int]  # the canvas's top-left, from the map area's
    share: float  # of the visible opaque canvas pixels, drawn exactly
    visible: int  # how many opaque canvas pixels are in view
    runner_up: float | None  # best score 3+ px away, relative to the best's;
    # None when kept near last frame's placement (no full search this frame)


def _share_at(hay: np.ndarray, info: MapInfo, at: tuple[int, int]) -> tuple[float, int]:
    ah, aw = hay.shape[:2]
    py, px = info.ys + at[1], info.xs + at[0]
    inside = (py >= 0) & (py < ah) & (px >= 0) & (px < aw)
    n = int(inside.sum())
    if n == 0:
        return 0.0, 0
    got = hay[py[inside], px[inside]]
    return float(np.all(got == info.colours[inside], axis=1).mean()), n


def _counts(
    hay: np.ndarray, info: MapInfo, off_x: np.ndarray, off_y: np.ndarray, sample: int
) -> np.ndarray:
    """How many of a sample of opaque canvas pixels are drawn exactly at every
    placement `off_x` x `off_y`, as a len(off_y) x len(off_x) array."""
    ah, aw = hay.shape[:2]
    step = max(1, len(info.ys) // sample)
    sy, sx, sc = info.ys[::step], info.xs[::step], info.colours[::step]
    # Pack BGR into one int so a comparison is one op.
    hay32 = (
        (hay[:, :, 0].astype(np.int32) << 16)
        | (hay[:, :, 1].astype(np.int32) << 8)
        | hay[:, :, 2]
    )
    sc32 = (
        (sc[:, 0].astype(np.int32) << 16) | (sc[:, 1].astype(np.int32) << 8) | sc[:, 2]
    )
    counts = np.zeros((len(off_y), len(off_x)), dtype=np.int32)
    px = sx[None, :] + off_x[:, None]
    inside_x = (px >= 0) & (px < aw)
    pxc = np.clip(px, 0, aw - 1)
    for i, dy in enumerate(off_y):
        py = sy + dy
        inside = ((py >= 0) & (py < ah))[None, :] & inside_x
        got = hay32[np.clip(py, 0, ah - 1)[None, :], pxc]
        counts[i] = ((got == sc32[None, :]) & inside).sum(axis=1)
    return counts


def place_canvas(
    hay: np.ndarray,
    info: MapInfo,
    hint: tuple[int, int] | None = None,
    sample: int = SAMPLE,
) -> Placement | None:
    """Where `info`'s canvas sits in the map area `hay` (BGR), or None when no
    placement shows any of it. Near `hint` first, then everywhere."""
    ah, aw = hay.shape[:2]
    cw, ch = info.size
    off_x, off_y = _offsets(aw, cw), _offsets(ah, ch)
    if hint is not None:
        near_x = off_x[np.abs(off_x - hint[0]) <= 4]
        near_y = off_y[np.abs(off_y - hint[1]) <= 8]
        if len(near_x) and len(near_y):
            counts = _counts(hay, info, near_x, near_y, sample)
            i, j = np.unravel_index(int(np.argmax(counts)), counts.shape)
            at = (int(near_x[j]), int(near_y[i]))
            share, visible = _share_at(hay, info, at)
            if share >= MATCHED_SHARE and visible >= MIN_VISIBLE:
                # The full search's runner-up was checked when this was found.
                return Placement(at, share, visible, None)
    counts = _counts(hay, info, off_x, off_y, sample)
    i, j = np.unravel_index(int(np.argmax(counts)), counts.shape)
    best = int(counts[i, j])
    if best == 0:
        return None
    at = (int(off_x[j]), int(off_y[i]))
    far = counts.copy()
    yy, xx = np.ogrid[: len(off_y), : len(off_x)]
    far[(np.abs(yy - i) < 3) & (np.abs(xx - j) < 3)] = 0
    share, visible = _share_at(hay, info, at)
    return Placement(at, share, visible, float(far.max()) / best)


# ── The tracker ─────────────────────────────────────────────────────────────


@dataclass
class Result:
    status: str  # "read", "unsure", "covered", "absent"
    detail: str
    located: Located | None = None
    placement: Placement | None = None
    canvas_xy: tuple[int, int] | None = None
    world_xy: tuple[int, int] | None = None
    ms: float = 0.0


class Tracker:
    def __init__(self, data: GameData, map_spec: str) -> None:
        self.data = data
        self.auto = map_spec.lower() == "auto"
        self.map: MapInfo | None = None if self.auto else data.map(map_spec)
        self.finder = FrameFinder(data.sprites)
        self.user = data.sprites.canvas(USER)
        self.hint: tuple[int, int] | None = None
        self._candidates: list[MapInfo] | None = None
        self._last_identify = -1e9
        self.identify_every = 2.0  # seconds between identifications when lost

    def candidates(self) -> list[MapInfo]:
        if self._candidates is None:
            self._candidates = self.data.all_maps()
        return self._candidates

    def identify(self, hay: np.ndarray) -> tuple[MapInfo, Placement] | None:
        """The map whose canvas is drawn in `hay`: a cheap sampled score of every
        canvas, then a full check of the best few."""
        scored = []
        for info in self.candidates():
            p = place_canvas(hay, info, sample=60)
            if p is not None and p.visible >= MIN_VISIBLE:
                scored.append((p.share, info))
        scored.sort(key=lambda s: -s[0])
        for _, info in scored[:5]:
            p = place_canvas(hay, info)
            if (
                p is not None
                and p.share >= MATCHED_SHARE
                and p.visible >= MIN_VISIBLE
                and (p.runner_up or 0) < AMBIGUOUS
            ):
                return info, p
        return None

    def step(self, px: np.ndarray, now: float | None = None) -> Result:
        start = time.perf_counter()
        result = self._step(px, time.monotonic() if now is None else now)
        result.ms = (time.perf_counter() - start) * 1000
        return result

    def _step(self, px: np.ndarray, now: float) -> Result:
        located = self.finder.find(px)
        if located is None:
            return Result(
                "absent",
                "minimap frame not found (closed, covered, or another UI on it)",
            )
        if located.area is None:
            return Result("unsure", "minimap is minimised: expand it", located)
        a = located.area
        if a.w <= 0 or a.h <= 0:
            return Result("unsure", "map area has no size", located)
        hay = np.ascontiguousarray(px[a.y : a.y + a.h, a.x : a.x + a.w])

        placement = None
        if self.map is not None:
            placement = place_canvas(hay, self.map, self.hint)
            ok = (
                placement is not None
                and placement.share >= MATCHED_SHARE
                and placement.visible >= MIN_VISIBLE
            )
            if not ok and self.auto:
                self.map, self.hint = None, None
        if self.map is None:
            if now - self._last_identify < self.identify_every:
                return Result("unsure", "map not identified (retrying)", located)
            self._last_identify = now
            found = self.identify(hay)
            if found is None:
                return Result(
                    "unsure",
                    "map not identified: no canvas matches the minimap",
                    located,
                )
            self.map, placement = found
        assert self.map is not None
        if placement is None:
            return Result(
                "unsure", f"map {self.map.id}'s canvas shows nothing here", located
            )
        if placement.visible < MIN_VISIBLE:
            return Result(
                "unsure",
                f"only {placement.visible} canvas px in view",
                located,
                placement,
            )
        if placement.share < MATCHED_SHARE:
            return Result(
                "unsure",
                f"map {self.map.id}'s minimap not drawn here ({placement.share:.0%})",
                located,
                placement,
            )
        if placement.runner_up is not None and placement.runner_up >= AMBIGUOUS:
            self.hint = None
            return Result(
                "unsure",
                f"canvas placement ambiguous (runner-up {placement.runner_up:.0%})",
                located,
                placement,
            )
        self.hint = placement.offset

        uh, uw = self.user.rgba.shape[:2]
        region = (a.x - uw, a.y - uh, a.w + 2 * uw, a.h + 2 * uh)
        hits = match(px, self.user.rgba, region, TOLERANCE)
        if not hits:
            return Result(
                "covered",
                "character marker not found (covered or at the edge)",
                located,
                placement,
            )
        hit = min(hits, key=lambda h: h.error)
        ox, oy = placement.offset
        cx = hit.x + self.user.origin[0] - a.x - ox
        cy = hit.y + self.user.origin[1] - a.y - oy
        detail = f"{len(hits)} markers matched" if len(hits) > 1 else ""
        return Result(
            "read", detail, located, placement, (cx, cy), self.map.world((cx, cy))
        )


# ── Frame sources ───────────────────────────────────────────────────────────


class LiveSource:
    """Captures the client with Desktop Duplication. Never sends input."""

    def __init__(self) -> None:
        from botting.screen import frame_source
        from maple.screen.client import find_client

        self.handle = find_client()
        self.source = frame_source()
        self.name = f"live window {self.handle}"

    def next(self) -> tuple[np.ndarray | None, str, str]:
        frame = self.source.grab(self.handle)
        if frame.pixels.size == 0 or (not frame.ok and not frame.pixels.any()):
            return None, "", frame.reason
        # A frame that isn't `ok` (the client not in front) is still read: the
        # canvas check rejects pixels that aren't the minimap.
        return frame.pixels, "", frame.reason


class FolderSource:
    def __init__(self, folder: Path) -> None:
        self.files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".png")
        if not self.files:
            raise SystemExit(f"no PNG in {folder}")
        self.index = 0
        self.playing = True

    def current(self) -> tuple[np.ndarray | None, str, str]:
        path = self.files[self.index]
        px = cv2.imread(str(path), cv2.IMREAD_COLOR)
        return px, path.name, ""

    def step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.files)


# ── The viewer ──────────────────────────────────────────────────────────────

GREEN, RED, YELLOW, CYAN, GREY, WHITE = (
    (80, 220, 80),
    (60, 60, 255),
    (0, 220, 255),
    (255, 200, 0),
    (140, 140, 140),
    (235, 235, 235),
)


PAD = 24
"""Canvas pixels drawn around the canvas, so a map area wider than it shows."""


def _canvas_image(info: MapInfo, scale: int) -> np.ndarray:
    rgba = info.canvas.rgba.astype(np.float32)
    alpha = rgba[:, :, 3:4] / 255
    bg = np.full(rgba.shape[:2] + (3,), 40, np.float32)
    bgr = rgba[:, :, 2::-1] * alpha + bg * (1 - alpha)
    img = cv2.copyMakeBorder(
        bgr.astype(np.uint8),
        PAD,
        PAD,
        PAD,
        PAD,
        cv2.BORDER_CONSTANT,
        value=(15, 15, 15),
    )
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)


class Viewer:
    TITLE = "minimap tracker (capture only)"

    def __init__(self, max_w: int = 1100, max_h: int = 760) -> None:
        self.max_w, self.max_h = max_w, max_h
        self.trail: deque[tuple[int, int]] = deque(maxlen=80)
        self._cache: tuple[int, int, np.ndarray] | None = None
        self.last_map: int | None = None

    def scale_for(self, info: MapInfo) -> int:
        w, h = info.size
        return max(1, min(4, self.max_w // (w + 2 * PAD), self.max_h // (h + 2 * PAD)))

    def render(
        self,
        px: np.ndarray | None,
        tracker: Tracker,
        r: Result,
        fps: float,
        source: str,
        note: str,
    ) -> np.ndarray:
        info = tracker.map
        if info is not None and info.id != self.last_map:
            self.trail.clear()
            self.last_map = info.id
        if r.status == "read" and r.canvas_xy is not None:
            self.trail.append(r.canvas_xy)

        # Left: the raw minimap, as captured.
        if px is not None and r.located is not None:
            b = r.located.bounds
            crop = px[max(0, b.y) : b.y + b.h, max(0, b.x) : b.x + b.w]
            k = max(
                1, min(3, 300 // max(1, crop.shape[1]), 420 // max(1, crop.shape[0]))
            )
            raw = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
        else:
            raw = np.zeros((120, 200, 3), np.uint8)
            cv2.putText(
                raw, "no minimap", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, GREY, 1
            )

        # Right: the map's whole canvas, the window, the trail and the dot.
        if info is not None:
            s = self.scale_for(info)
            if self._cache is None or self._cache[:2] != (info.id, s):
                self._cache = (info.id, s, _canvas_image(info, s))
            right = self._cache[2].copy()
            if (
                r.placement is not None
                and r.located is not None
                and r.located.area is not None
            ):
                ox, oy = r.placement.offset
                a = r.located.area
                colour = YELLOW if r.status in ("read", "covered") else GREY
                x0, y0 = (PAD - ox) * s, (PAD - oy) * s
                cv2.rectangle(
                    right, (x0, y0), (x0 + a.w * s - 1, y0 + a.h * s - 1), colour, 1
                )
            pts = [((x + PAD) * s, (y + PAD) * s) for x, y in self.trail]
            for p, q in itertools.pairwise(pts):
                cv2.line(right, p, q, CYAN, 1)
            if pts:
                last = pts[-1]
                if r.status == "read":
                    cv2.circle(right, last, max(4, s + 2), RED, -1)
                    cv2.circle(right, last, max(4, s + 2), WHITE, 1)
                else:
                    cv2.circle(
                        right, last, max(4, s + 2), GREY, 1
                    )  # last known, not current
        else:
            right = np.zeros((200, 400, 3), np.uint8)
            cv2.putText(
                right,
                "map not identified",
                (10, 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                GREY,
                1,
            )

        # Status lines.
        word = {
            "read": "READ",
            "covered": "COVERED",
            "unsure": "UNSURE",
            "absent": "ABSENT",
        }[r.status]
        colour = GREEN if r.status == "read" else RED
        lines: list[tuple[str, tuple[int, int, int]]] = [
            (f"{word}  {r.detail}", colour),
            (
                f"map: {info.label if info else '?'}"
                + ("  [auto]" if tracker.auto else ""),
                WHITE,
            ),
        ]
        if r.status == "read" and r.canvas_xy and r.world_xy:
            lines.append((f"canvas px: {r.canvas_xy}   world px: {r.world_xy}", WHITE))
        else:
            lines.append(("canvas px: --   world px: --", GREY))
        if r.placement is not None:
            p = r.placement
            runner = "tracked" if p.runner_up is None else f"{p.runner_up:.0%}"
            lines.append(
                (
                    f"confidence: {p.share:.0%} of {p.visible} canvas px drawn; runner-up {runner}; offset {p.offset}",
                    WHITE,
                )
            )
        if r.located is not None and r.located.area is not None:
            a = r.located.area
            cw, ch = info.size if info else (0, 0)
            lines.append(
                (
                    f"look {r.located.look}, area {a.w}x{a.h} at ({a.x},{a.y}); canvas {cw}x{ch}",
                    GREY,
                )
            )
        lines.append((f"{fps:5.1f} fps   tracker {r.ms:5.1f} ms   {source}", GREY))
        if note:
            lines.append((note, YELLOW))

        width = max(raw.shape[1] + 10 + right.shape[1], 760)
        top_h = max(raw.shape[0], right.shape[0])
        out = np.full((top_h + 22 * len(lines) + 12, width, 3), 20, np.uint8)
        out[: raw.shape[0], : raw.shape[1]] = raw
        out[
            : right.shape[0], raw.shape[1] + 10 : raw.shape[1] + 10 + right.shape[1]
        ] = right
        for i, (text, c) in enumerate(lines):
            cv2.putText(
                out,
                text,
                (8, top_h + 20 + 22 * i),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                c,
                1,
                cv2.LINE_AA,
            )
        return out


# ── Offline accuracy against labels ─────────────────────────────────────────


def evaluate(data: GameData, map_spec: str, folder: Path, labels_path: Path) -> None:
    frames = json.loads(labels_path.read_text())["frames"]
    labels = {f["file"]: f["expect"].get("minimap") for f in frames}
    sizes = {
        f["file"]: "x".join(map(str, f.get("client_size") or ("?",))) for f in frames
    }
    files = sorted(p for p in folder.iterdir() if p.name in labels)
    for mode in ("sequential", "cold"):
        tracker = Tracker(data, map_spec)
        tracker.identify_every = 0.0
        stats = {
            "exact": 0,
            "off": 0,
            "unsure_on_read": 0,
            "fake_read": 0,
            "ok_unsure": 0,
            "read_total": 0,
        }
        by_size: dict[str, list[int]] = {}
        wrong: list[str] = []
        times: list[float] = []
        for path in files:
            if mode == "cold":
                tracker = Tracker(data, map_spec)
                tracker.identify_every = 0.0
            px = cv2.imread(str(path), cv2.IMREAD_COLOR)
            r = tracker.step(px)
            times.append(r.ms)
            lab = labels[path.name] or {}
            val = lab.get("value") or {}
            expected = val.get("self_position") if lab.get("status") == "read" else None
            size = sizes[path.name]
            cell = by_size.setdefault(
                f"{(val.get('map') or 'none')[:22]:22} {size}", [0, 0]
            )
            if expected is not None:
                stats["read_total"] += 1
                cell[1] += 1
                # The label's map must also be the map tracked.
                right_map = (
                    tracker.map is not None
                    and (val.get("map") or "") in tracker.map.label
                )
                if r.status == "read" and right_map and tuple(expected) == r.canvas_xy:
                    stats["exact"] += 1
                    cell[0] += 1
                elif r.status == "read":
                    stats["off"] += 1
                    wrong.append(
                        f"{path.name}: got {r.canvas_xy} on {tracker.map.label if tracker.map else '?'}, want {tuple(expected)}"
                    )
                else:
                    stats["unsure_on_read"] += 1
                    wrong.append(
                        f"{path.name}: {r.status} ({r.detail}), want {tuple(expected)}"
                    )
            elif r.status == "read":
                stats["fake_read"] += 1
                wrong.append(
                    f"{path.name}: read {r.canvas_xy} but label is {lab.get('status')}/{val.get('state')}"
                )
            else:
                stats["ok_unsure"] += 1
        t = np.array(times)
        print(f"\n== {mode} (map={map_spec}) on {len(files)} frames ==")
        print(
            f"labelled positions: {stats['read_total']}, exact {stats['exact']}, "
            f"wrong {stats['off']}, unsure {stats['unsure_on_read']}; "
            f"no-position frames: {stats['ok_unsure'] + stats['fake_read']}, read anyway {stats['fake_read']}"
        )
        print(
            f"tracker ms: median {np.median(t):.1f}, p90 {np.percentile(t, 90):.1f}, max {t.max():.1f}"
        )
        for k, (ok, n) in sorted(by_size.items()):
            if n:
                print(f"  {k}: {ok}/{n}")
        for line in wrong:
            print("   ", line)


# ── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--map",
        required=True,
        help="map name or id, or 'auto' to identify it from the minimap",
    )
    ap.add_argument(
        "--frames",
        type=Path,
        help="replay the PNGs in this folder instead of capturing",
    )
    ap.add_argument(
        "--labels",
        type=Path,
        help="with --frames: a frame-set labels JSON, to score accuracy",
    )
    ap.add_argument(
        "--headless",
        action="store_true",
        help="with --labels: print accuracy, open no window",
    )
    ap.add_argument(
        "--log",
        type=Path,
        help="write time, canvas x/y, world x/y, confidence to this CSV",
    )
    ap.add_argument(
        "--store",
        type=Path,
        default=None,
        help="game_data store root (default: data/game_data)",
    )
    ap.add_argument(
        "--fps",
        type=float,
        default=0,
        help="cap the capture rate (0: as fast as it goes)",
    )
    args = ap.parse_args()

    store = args.store or default_store()
    data = GameData(store)
    print(f"game data: {store} build {data.sprites.build}")
    try:
        if args.labels:
            if not args.frames:
                raise SystemExit("--labels needs --frames")
            evaluate(data, args.map, args.frames, args.labels)
            if args.headless:
                return
        run(data, args)
    finally:
        data.close()


def run(data: GameData, args: argparse.Namespace) -> None:
    tracker = Tracker(data, args.map)
    if tracker.map is not None:
        print(f"tracking {tracker.map.label}, canvas {tracker.map.size}")
    folder = FolderSource(args.frames) if args.frames else None
    live = None if folder else LiveSource()
    viewer = Viewer()
    log = None
    writer = None
    if args.log:
        log = args.log.open("w", newline="")
        writer = csv.writer(log)
        writer.writerow(
            [
                "time",
                "frame",
                "status",
                "canvas_x",
                "canvas_y",
                "world_x",
                "world_y",
                "confidence",
                "map_id",
            ]
        )
    fps = 0.0
    last = time.perf_counter()
    t0 = last
    try:
        while True:
            if folder is not None:
                px, name, note = folder.current()
                source = f"{name} [{folder.index + 1}/{len(folder.files)}]" + (
                    "" if folder.playing else " paused"
                )
                if folder.playing:
                    tracker.identify_every = 0.0
            else:
                assert live is not None
                px, name, note = live.next()
                source = live.name
            r = (
                tracker.step(px)
                if px is not None
                else Result("absent", note or "no frame")
            )
            now = time.perf_counter()
            dt = now - last
            last = now
            fps = (1 / dt if fps == 0 else 0.9 * fps + 0.1 / dt) if dt > 0 else fps
            if writer is not None:
                c = r.canvas_xy or ("", "")
                w = r.world_xy or ("", "")
                conf = f"{r.placement.share:.3f}" if r.placement else ""
                writer.writerow(
                    [
                        f"{now - t0:.3f}",
                        name,
                        r.status,
                        *c,
                        *w,
                        conf,
                        tracker.map.id if tracker.map else "",
                    ]
                )
            cv2.imshow(Viewer.TITLE, viewer.render(px, tracker, r, fps, source, note))
            wait = 1
            if folder is not None:
                wait = 300 if folder.playing else 0
            elif args.fps > 0:
                wait = max(1, int(1000 / args.fps - (time.perf_counter() - now) * 1000))
            key = cv2.waitKey(wait) & 0xFF
            if key in (ord("q"), 27):
                break
            if cv2.getWindowProperty(Viewer.TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("c"):
                viewer.trail.clear()
            if key == ord("r") and tracker.auto:
                tracker.map, tracker.hint, tracker._last_identify = None, None, -1e9
            if folder is not None:
                if key == ord(" "):
                    folder.playing = not folder.playing
                elif key == ord("p"):
                    folder.step(-1)
                elif key == ord("n") or folder.playing:
                    folder.step(1)
    finally:
        if log is not None:
            log.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
