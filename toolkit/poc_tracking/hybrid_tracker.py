"""
Hybrid tracker (proof of concept): the character's position read two ways at
once, from the minimap and from the play area, each checking the other.

**Capture only. This script never sends a key, a click or any other input to the
game.** It copies the client's pixels (Desktop Duplication, `botting.screen`)
and draws in its own OpenCV window; the only keys it reads are the ones pressed
in that window. It doesn't import anything that sends input.

    python toolkit/poc_tracking/hybrid_tracker.py --map "Ellinia" --store <store>
    python toolkit/poc_tracking/hybrid_tracker.py --map 10005031 --frames <dir>

Two estimates, both in virtual coordinates (the map's own, `CONTEXT.md`):

- **Minimap.** The minimap's frame (`UI/MiniMap.img/MaxMap` or `MinMap`) gives
  the map area. The map's own `miniMap/canvas` is placed in it by exact colour
  (it may be centred, or scroll on either axis), the `user` marker is found, and
  its canvas pixel becomes `c * 2**mag - centre`. Its precision is one canvas
  pixel (16 virtual px at mag 4).
- **World.** The camera (the play area's top-left, in virtual coordinates) is
  found by exact-colour voting of the frame against `game_data`'s render of the
  map's static layers (tiles, objects, backgrounds fixed to the map), seeded by
  the last camera, else over the whole map. A client wider than 1366 is taken to
  draw its play area at 1366 wide and upscale it: the frame is downscaled and the
  camera found by masked normalised correlation, seeded by the last camera or the
  minimap. The character is then the camera plus its feet on screen: from YOLO's
  `Character` box when weights are given and present, otherwise from its name
  tag (white text on a dark box drawn just under the feet).

**Fusion.** Both read: the world position predicts which canvas pixel the
marker should be on (`MARKER_ROWS_ABOVE`); within one pixel they "agree" (the
world estimate is kept, it is the finer one), otherwise "DISAGREE" (no fused
position: unsure). One read: that one. Neither: unsure.
The minimap also cross-checks the camera: a camera candidate that would put the
minimap's position off screen is rejected.

Everything comes from the `game_data` store; there is no hand-made map file.
"""

from __future__ import annotations

import argparse
import collections
import csv
import math
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from botting.screen import match, match_best, matches_at
from game_data.catalogue import Catalogue
from game_data.catalogue.model import MapData
from game_data.config import STORE
from game_data.render import STORED_AT_RX, render_map
from game_data.sprites import Sprite, Sprites

PLAY_WIDTH = 1366
"""A client wider than this is taken to draw its play area this wide and
upscale it (measured at 1920x1080 only)."""
MAX_OCCURRENCES = 64
"""Colours drawn more often than this in the static render don't vote."""
MINIMAP_SHARE_OK = 0.6
"""The share of the canvas's visible opaque pixels drawn exactly for the canvas
to count as found (#365's `MATCHED_SHARE`)."""
CAMERA_SHARE_OK = 0.2
"""The exact share at a voted camera for it to count (right answers measured
0.33 or more, wrong ones 0.02 or less)."""
CAMERA_VOTES_OK = 5
NCC_OK = 0.85
"""The masked correlation score for a camera on a scaled client."""
MARKER_ROWS_ABOVE = 6
"""The `user` marker's centre is drawn this many canvas rows above the canvas
pixel the feet are in: canvas = (floor((x + cx) / 2**mag), floor((y + cy) /
2**mag) - 6). It held exactly in y on all 91 frames of set v2 where both
sources read (hybrid_tracker.md). As if the client anchored the 12x12 marker by
its bottom centre rather than its origin (6, 6): unverified."""
TAG_TO_FEET = 5
"""The name tag's white text starts this many play-area px below the feet
(calibrated on frame set v2 against footholds)."""
MODEL = REPO / "data" / "models" / "production" / "global" / "weights" / "best.pt"


# --------------------------------------------------------------------------- map


class _StaticOnly:
    """A catalogue whose `map_layers` keeps tiles, objects, and the backgrounds
    fixed to the map: what the client draws the same at every camera."""

    def __init__(self, cat: Catalogue) -> None:
        self._cat = cat

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cat, name)

    def map_layers(self, map_id: str | int) -> list[Any]:
        return [
            item
            for item in self._cat.map_layers(map_id)
            if item.kind != "back"
            or (
                item.background is not None
                and item.background.rx == STORED_AT_RX
                and item.background.ry == STORED_AT_RX
            )
        ]


class ColourIndex:
    """The static render's opaque pixels, by exact colour, for voting."""

    def __init__(self, static_rgba: np.ndarray) -> None:
        self.height, self.width = static_rgba.shape[:2]
        ys, xs = np.nonzero(static_rgba[:, :, 3] == 255)
        px = static_rgba[ys, xs].astype(np.int64)
        key = (px[:, 2] << 16) | (px[:, 1] << 8) | px[:, 0]  # BGR, as captured
        order = np.argsort(key, kind="stable")
        key, ys, xs = key[order], ys[order], xs[order]
        colours, count = np.unique(key, return_counts=True)
        keep = count <= MAX_OCCURRENCES
        kept = np.repeat(keep, count)
        self.keys = colours[keep]
        self.count = count[keep]
        self.start = np.concatenate(([0], np.cumsum(self.count)[:-1])).astype(np.int64)
        self.xs = xs[kept].astype(np.int32)
        self.ys = ys[kept].astype(np.int32)


def bgr_keys(pixels: np.ndarray) -> np.ndarray:
    p = pixels.astype(np.int64)
    return (p[..., 0] << 16) | (p[..., 1] << 8) | p[..., 2]


@dataclass
class MapAssets:
    data: MapData
    build: str
    canvas: Sprite
    user: Sprite
    looks: list[tuple[str, Sprite, Sprite, Sprite]]  # name, nw, n, se
    static: np.ndarray  # RGBA, VR top-left at (0, 0)
    static_bgr: np.ndarray
    static_opaque: np.ndarray
    full: np.ndarray  # BGR, for display
    index: ColourIndex

    @property
    def origin(self) -> tuple[int, int]:
        """The render's pixel (0, 0), in virtual coordinates."""
        return self.data.vr.left, self.data.vr.top


def resolve_map(cat: Catalogue, text: str) -> MapData:
    """A map by ID, or a name that names one only (`Catalogue.map`'s rules)."""
    return cat.map(int(text) if text.isdigit() else text)


def load_assets(store: Path, map_text: str, cache: Path) -> MapAssets:
    t0 = time.perf_counter()
    with Catalogue.latest(store) as cat:
        data = resolve_map(cat, map_text)
        if data.minimap is None:
            raise SystemExit(f"map {data.id} has no miniMap node")
        folder = cache / cat.build
        folder.mkdir(parents=True, exist_ok=True)
        static = _cached(
            folder / f"{data.id}_static.png",
            lambda: render_map(cast(Catalogue, _StaticOnly(cat)), data.id),
        )
        full = _cached(folder / f"{data.id}_full.png", lambda: render_map(cat, data.id))
        build = cat.build
    with Sprites.latest(store) as sprites:
        canvas = sprites.canvas(
            f"Map/Map/Map{data.id // 100_000_000}/{data.id:09d}.img/miniMap/canvas"
        )
        user = sprites.canvas("Map/MapHelper.img/minimap/user")
        looks = [
            (
                look,
                sprites.canvas(f"UI/MiniMap.img/{look}/nw"),
                sprites.canvas(f"UI/MiniMap.img/{look}/n"),
                sprites.canvas(f"UI/MiniMap.img/{look}/se"),
            )
            for look in ("MaxMap", "MinMap")
        ]
    index = ColourIndex(static)
    full_bgr = np.ascontiguousarray(full[:, :, 2::-1])
    print(
        f"map {data.id} {data.street}: {data.name}; render {static.shape[1]}x"
        f"{static.shape[0]}, minimap canvas {canvas.rgba.shape[1]}x"
        f"{canvas.rgba.shape[0]} mag {data.minimap.mag}; "
        f"{len(index.keys)} voting colours; loaded in {time.perf_counter() - t0:.1f}s"
    )
    return MapAssets(
        data,
        build,
        canvas,
        user,
        looks,
        static,
        np.ascontiguousarray(static[:, :, 2::-1]),
        static[:, :, 3] == 255,
        full_bgr,
        index,
    )


def _cached(path: Path, render: Any) -> np.ndarray:
    if path.exists():
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        return np.ascontiguousarray(image[:, :, [2, 1, 0, 3]])
    rgba = render()
    cv2.imwrite(str(path), rgba[:, :, [2, 1, 0, 3]])
    return rgba


# ------------------------------------------------------------------------ minimap


@dataclass
class MinimapEstimate:
    ok: bool
    status: str
    area: tuple[int, int, int, int] | None = None  # x0, y0, x1, y1 on screen
    canvas_at: tuple[int, int] | None = None  # the canvas's top-left on screen
    canvas_pos: tuple[int, int] | None = None
    world: tuple[float, float] | None = None  # the marker, as #365 converts it
    feet: tuple[float, float] | None = None  # where the marker puts the feet
    share: float = 0.0
    ms: float = 0.0


def _offsets(area: int, length: int) -> np.ndarray:
    """The canvas's possible offsets in the map area along one axis: inside it
    where it fits, a window on it where it's longer (it scrolls)."""
    if length <= area:
        return np.arange(0, area - length + 1)
    return np.arange(area - length, 1)


class MinimapTracker:
    """The minimap's frame, the canvas in its map area, the `user` marker."""

    def __init__(self, assets: MapAssets) -> None:
        self.a = assets
        rgba = assets.canvas.rgba
        ys, xs = np.nonzero(rgba[:, :, 3] == 255)
        self._ys, self._xs = ys, xs
        p = rgba[ys, xs].astype(np.int64)
        self._keys = (p[:, 2] << 16) | (p[:, 1] << 8) | p[:, 0]
        step = max(1, len(ys) // 400)
        self._sample = slice(None, None, step)
        self._look = 0
        self._nw_at: tuple[int, int] | None = None
        self._se_off: tuple[int, int] | None = None
        self._canvas_off: tuple[int, int] | None = None
        self.search_cooldown = 0.0
        self._search_after = 0.0

    def read(self, frame: np.ndarray) -> MinimapEstimate:
        t0 = time.perf_counter()
        est = self._read(frame)
        est.ms = (time.perf_counter() - t0) * 1e3
        return est

    def _read(self, frame: np.ndarray) -> MinimapEstimate:
        area = self._area(frame)
        if area is None:
            return MinimapEstimate(False, "minimap not found (closed or minimised?)")
        x0, y0, x1, y1 = area
        if x1 - x0 < 4 or y1 - y0 < 4:
            return MinimapEstimate(False, "map area too small", area)
        hay = bgr_keys(frame[y0:y1, x0:x1])
        placed = self._place(hay)
        if placed is None or placed[1] < MINIMAP_SHARE_OK:
            share = 0.0 if placed is None else placed[1]
            return MinimapEstimate(
                False,
                f"map canvas not found ({share:.0%}): wrong map?",
                area,
                share=share,
            )
        (ox, oy), share = placed
        self._canvas_off = (ox, oy)
        canvas_at = (x0 + ox, y0 + oy)
        user = self.a.user
        uh, uw = user.rgba.shape[:2]
        hit = match_best(
            frame, user.rgba, (x0 - uw, y0 - uh, x1 - x0 + 2 * uw, y1 - y0 + 2 * uh)
        )
        if hit is None:
            return MinimapEstimate(
                False, "user marker not found (covered?)", area, canvas_at, share=share
            )
        cx = hit.x + user.origin[0] - canvas_at[0]
        cy = hit.y + user.origin[1] - canvas_at[1]
        mm = self.a.data.minimap
        assert mm is not None
        k = 2**mm.mag
        world = (cx * k - mm.center_x, cy * k - mm.center_y)
        # The middle of the canvas pixel the feet are in.
        feet = (world[0] + k / 2, world[1] + MARKER_ROWS_ABOVE * k + k / 2)
        return MinimapEstimate(
            True, "read", area, canvas_at, (cx, cy), world, feet, share
        )

    def _area(self, frame: np.ndarray) -> tuple[int, int, int, int] | None:
        order = [self._look] + [i for i in range(len(self.a.looks)) if i != self._look]
        if self._nw_at is not None and self._se_off is not None:
            _, nw, n, se = self.a.looks[self._look]
            x, y = self._nw_at
            sx, sy = x + self._se_off[0], y + self._se_off[1]
            if matches_at(frame, nw.rgba, x, y) and matches_at(frame, se.rgba, sx, sy):
                return self._box(nw, (x, y), (sx, sy))
        if time.monotonic() < self._search_after:
            return None
        h, w = frame.shape[:2]
        for i in order:
            _, nw, n, se = self.a.looks[i]
            nh, nww = nw.rgba.shape[:2]
            for hit in sorted(match(frame, nw.rgba), key=lambda h: h.error)[:8]:
                if not matches_at(frame, n.rgba, hit.x + nww, hit.y):
                    continue
                found = match(frame, se.rgba, (hit.x + nww, hit.y + nh, w, h))
                if not found:
                    continue
                s = min(found, key=lambda f: (f.x - hit.x) + (f.y - hit.y))
                self._look, self._nw_at = i, (hit.x, hit.y)
                self._se_off = (s.x - hit.x, s.y - hit.y)
                self._canvas_off = None
                return self._box(nw, (hit.x, hit.y), (s.x, s.y))
        self._nw_at = None
        # A whole-frame search costs ~200 ms: live, don't repeat it every frame
        # while the minimap is closed or minimised.
        self._search_after = time.monotonic() + self.search_cooldown
        return None

    @staticmethod
    def _box(
        nw: Sprite, at: tuple[int, int], se: tuple[int, int]
    ) -> tuple[int, int, int, int]:
        nh, nww = nw.rgba.shape[:2]
        return at[0] + nww, at[1] + nh, se[0], se[1]

    def _place(self, hay: np.ndarray) -> tuple[tuple[int, int], float] | None:
        ah, aw = hay.shape
        ch, cw = self.a.canvas.rgba.shape[:2]
        off_x, off_y = _offsets(aw, cw), _offsets(ah, ch)
        if self._canvas_off is not None:
            hx, hy = self._canvas_off
            near_x = off_x[np.abs(off_x - hx) <= 6]
            near_y = off_y[np.abs(off_y - hy) <= 6]
            if len(near_x) and len(near_y):
                found = self._best(hay, near_x, near_y)
                if found is not None and found[1] >= MINIMAP_SHARE_OK:
                    return found
        return self._best(hay, off_x, off_y)

    def _best(
        self, hay: np.ndarray, off_x: np.ndarray, off_y: np.ndarray
    ) -> tuple[tuple[int, int], float] | None:
        ah, aw = hay.shape
        sy, sx, sk = (
            self._ys[self._sample],
            self._xs[self._sample],
            self._keys[self._sample],
        )
        counts = np.zeros((len(off_y), len(off_x)), np.int64)
        px = sx[None, :] + off_x[:, None]
        inx = (px >= 0) & (px < aw)
        pxc = np.clip(px, 0, aw - 1)
        for i, dy in enumerate(off_y):
            py = sy + dy
            iny = (py >= 0) & (py < ah)
            got = hay[np.clip(py, 0, ah - 1)[None, :], pxc]
            counts[i] = ((got == sk[None, :]) & inx & iny[None, :]).sum(axis=1)
        i, j = np.unravel_index(int(np.argmax(counts)), counts.shape)
        at = (int(off_x[j]), int(off_y[i]))
        py, px1 = self._ys + at[1], self._xs + at[0]
        inside = (py >= 0) & (py < ah) & (px1 >= 0) & (px1 < aw)
        if not inside.any():
            return None
        share = float((hay[py[inside], px1[inside]] == self._keys[inside]).mean())
        return at, share


# -------------------------------------------------------------------------- world


@dataclass
class WorldEstimate:
    ok: bool
    status: str
    camera: tuple[int, int] | None = None  # play area top-left, virtual
    camera_conf: float = 0.0
    camera_method: str = ""
    scale: float = 1.0
    feet_screen: tuple[float, float] | None = None  # on the captured frame
    tag_box: tuple[int, int, int, int] | None = None
    char_conf: float = 0.0
    char_method: str = ""
    world: tuple[float, float] | None = None
    ms: float = 0.0
    ms_camera: float = 0.0


class WorldTracker:
    def __init__(self, assets: MapAssets, weights: Path | None, seed: int = 0) -> None:
        self.a = assets
        self.rng = np.random.default_rng(seed)
        self.last_cam: tuple[int, int] | None = None  # render px
        self.last_feet: tuple[float, float] | None = None  # virtual
        # The character's own name-tag text, once learned, for the frame size.
        self.tag_text: tuple[tuple[int, ...], np.ndarray] | None = None
        self.tag_widths: collections.Counter[int] = collections.Counter()
        self.yolo: Any = None
        if weights is not None and weights.exists():
            from ultralytics import YOLO  # only when weights are there

            self.yolo = YOLO(str(weights))
            print(f"character: YOLO {weights}")
        else:
            print(
                f"character: name-tag finder (no YOLO weights at {weights}; "
                "run scripts/fetch_models.py for them)"
            )

    # ---- camera

    def _vote(
        self,
        play: np.ndarray,
        k: int,
        seed: tuple[int, int] | None,
        radius: int,
    ) -> list[tuple[int, int, int]]:
        """Camera peaks (render px) with their votes, best first."""
        ix = self.a.index
        h, w = play.shape[:2]
        ys = self.rng.integers(0, h, k)
        xs = self.rng.integers(0, w, k)
        key = bgr_keys(play[ys, xs])
        i = np.clip(np.searchsorted(ix.keys, key), 0, len(ix.keys) - 1)
        hit = ix.keys[i] == key
        ys, xs, i = ys[hit], xs[hit], i[hit]
        if len(i) == 0:
            return []
        cnt = ix.count[i]
        rep = np.repeat(np.arange(len(i)), cnt)
        first = np.repeat(np.cumsum(cnt) - cnt, cnt)
        idx = ix.start[i][rep] + (np.arange(int(cnt.sum())) - first)
        cl = ix.xs[idx] - xs[rep]
        ct = ix.ys[idx] - ys[rep]
        if seed is not None:
            ok = (np.abs(cl - seed[0]) <= radius) & (np.abs(ct - seed[1]) <= radius)
            cl, ct = cl[ok], ct[ok]
        if len(cl) == 0:
            return []
        span = ix.width + 2 * w
        code = (ct.astype(np.int64) + h) * span + (cl.astype(np.int64) + w)
        codes, votes = np.unique(code, return_counts=True)
        top = np.argsort(votes)[::-1][:40]
        peaks: list[tuple[int, int, int]] = []
        for t in top:
            y, x = divmod(int(codes[t]), span)
            x, y = x - w, y - h
            if all(abs(x - px) > 3 or abs(y - py) > 3 for px, py, _ in peaks):
                peaks.append((x, y, int(votes[t])))
            if len(peaks) == 5:
                break
        return peaks

    def exact_share(self, play: np.ndarray, cl: int, ct: int, stride: int = 3) -> float:
        h, w = play.shape[:2]
        sh, sw = self.a.static_opaque.shape
        x0, y0 = max(0, cl), max(0, ct)
        x1, y1 = min(sw, cl + w), min(sh, ct + h)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        m = self.a.static_opaque[y0:y1:stride, x0:x1:stride]
        if m.sum() < 50:
            return 0.0
        ren = self.a.static_bgr[y0:y1:stride, x0:x1:stride]
        got = play[y0 - ct : y1 - ct : stride, x0 - cl : x1 - cl : stride]
        return float(np.all(ren[m] == got[m], axis=1).mean())

    def _plausible(
        self,
        cam: tuple[int, int],
        size: tuple[int, int],
        mm_world: tuple[float, float] | None,
    ) -> bool:
        """The minimap's cross-check: the feet it puts the character at must be
        on screen, give or take a margin."""
        if mm_world is None:
            return True
        vx, vy = self.a.origin
        sx = mm_world[0] - (cam[0] + vx)
        sy = mm_world[1] - (cam[1] + vy)
        m = 64
        return -m <= sx <= size[0] + m and -m <= sy <= size[1] + m

    def _camera_exact(
        self, play: np.ndarray, mm_world: tuple[float, float] | None
    ) -> tuple[tuple[int, int] | None, float, str]:
        size = (play.shape[1], play.shape[0])
        rejected = 0
        attempts: list[tuple[str, int, tuple[int, int] | None, int]] = []
        if self.last_cam is not None:
            attempts.append(("seeded vote", 1500, self.last_cam, 200))
        attempts.append(("global vote", 3000, None, 0))
        for name, k, seed, radius in attempts:
            for cl, ct, votes in self._vote(play, k, seed, radius):
                if votes < CAMERA_VOTES_OK:
                    break
                share = self.exact_share(play, cl, ct)
                if share < CAMERA_SHARE_OK:
                    continue
                if not self._plausible((cl, ct), size, mm_world):
                    rejected += 1
                    continue
                return (cl, ct), share, name
        why = "camera not found"
        if rejected:
            why += f" ({rejected} peak(s) rejected by the minimap)"
        return None, 0.0, why

    def _camera_scaled(
        self, play: np.ndarray, mm_world: tuple[float, float] | None
    ) -> tuple[tuple[int, int] | None, float, str]:
        """Masked normalised correlation, coarse to fine, around a seed."""
        seeds: list[tuple[tuple[int, int], int]] = []
        if self.last_cam is not None:
            seeds.append((self.last_cam, 96))
        if mm_world is not None:
            seeds.append((self._camera_from_minimap(mm_world, play.shape[:2]), 192))
        if not seeds:
            return None, 0.0, "scaled client: no seed (no minimap, no last camera)"
        score = 0.0
        for seed, radius in seeds:
            cam, score = _ncc_locate(self.a.static, play, seed, radius)
            if score >= NCC_OK:
                return cam, score, "ncc (scaled)"
        return None, score, f"ncc score {score:.2f} too low"

    def _camera_from_minimap(
        self, mm_world: tuple[float, float], size: tuple[int, int]
    ) -> tuple[int, int]:
        """The camera (render px) centred on the minimap's position, clamped to
        the map as the client clamps it. Only a seed: the real camera lags and
        sits off centre by an amount that depends on the client size."""
        h, w = size
        vx, vy = self.a.origin
        x = int(mm_world[0] - vx - w / 2)
        y = int(mm_world[1] - vy - h / 2)
        mh, mw = self.a.static.shape[:2]
        x = min(max(x, 0), mw - w) if mw >= w else (mw - w) // 2
        y = min(max(y, 0), mh - h) if mh >= h else (mh - h) // 2
        return x, y

    # ---- character

    def _feet(
        self,
        frame: np.ndarray,
        scale: float,
        guess: tuple[float, float] | None,
        guess_from_minimap: bool = False,
    ) -> tuple[
        tuple[float, float] | None, tuple[int, int, int, int] | None, float, str
    ]:
        """The feet on the captured frame, the tag's box, a confidence, how."""
        h, w = frame.shape[:2]
        if self.yolo is not None:
            res = self.yolo.predict(frame, verbose=False, conf=0.3)[0]
            best = None
            for box, cls, conf in zip(
                res.boxes.xyxy.tolist(),
                res.boxes.cls.tolist(),
                res.boxes.conf.tolist(),
                strict=True,
            ):
                if res.names[int(cls)] != "Character":
                    continue
                fx, fy = (box[0] + box[2]) / 2, box[3]
                d = 0.0 if guess is None else math.hypot(fx - guess[0], fy - guess[1])
                if best is None or d < best[0]:
                    best = (d, (fx, fy), conf, tuple(int(v) for v in box))
            if best is None:
                return None, None, 0.0, "yolo: no Character"
            return best[1], best[3], float(best[2]), "yolo"
        if guess is not None:
            gx, gy = guess
            rx0, rx1 = int(gx - 120 * scale), int(gx + 120 * scale)
            ry0, ry1 = int(gy - 60 * scale), int(gy + 200 * scale)
        else:
            rx0, rx1, ry0, ry1 = 0, w, 0, h
        rx0, ry0 = max(0, rx0), max(0, ry0)
        rx1, ry1 = min(w, rx1), min(h, ry1)
        if rx1 - rx0 < 20 or ry1 - ry0 < 20:
            return None, None, 0.0, "tag: search window off screen"
        region = frame[ry0:ry1, rx0:rx1]
        ref = (
            (guess[0] - rx0, guess[1] - ry0)
            if guess is not None
            else ((rx1 - rx0) / 2, (ry1 - ry0) / 2)
        )
        found = None
        if self.tag_text is not None and self.tag_text[0] == frame.shape:
            found = self._learned_tag(region, self.tag_text[1], ref, scale)
        how = "name tag (learned)"
        if found is None:
            how = "name tag"
            tags = find_name_tags(region, scale)
            if not tags:
                return None, None, 0.0, "tag: none found"
            tag = min(
                tags, key=lambda t: math.hypot(t.x + t.w / 2 - ref[0], t.y - ref[1])
            )
            found = (tag.x, tag.y, tag.w, tag.h, tag.dark)
            learned = self.tag_text is not None and self.tag_text[0] == frame.shape
            if learned and abs(tag.w - self.tag_text[1].shape[1]) > 4:  # type: ignore[index]
                # Not the learned text: another tag, or ours merged with one.
                return None, None, 0.0, "tag: only another tag, or ours merged with one"
            # Learn this character's own tag text once the same width has been
            # seen where the minimap puts the character a few times: other
            # tags drawn against it (another player's, a mob's) then can't pull
            # the read sideways. A tag merged with another has another width.
            if guess_from_minimap and abs(tag.x + tag.w / 2 - ref[0]) <= 16 * scale:
                self.tag_widths[tag.w] += 1
                if self.tag_widths[tag.w] >= 3:
                    text = region[tag.y : tag.y + tag.h, tag.x : tag.x + tag.w]
                    white = (text.min(axis=2) >= _white(scale)).astype(np.float32)
                    self.tag_text = (frame.shape, white)
        x, y, bw, bh, conf = found
        feet = (rx0 + x + bw / 2, ry0 + y - TAG_TO_FEET * scale)
        return feet, (rx0 + x, ry0 + y, rx0 + x + bw, ry0 + y + bh), conf, how

    @staticmethod
    def _learned_tag(
        region: np.ndarray, text: np.ndarray, ref: tuple[float, float], scale: float
    ) -> tuple[int, int, int, int, float] | None:
        """The learned tag text in `region`, nearest `ref` among good matches."""
        white = (region.min(axis=2) >= _white(scale)).astype(np.float32)
        th, tw = text.shape
        if white.shape[0] < th or white.shape[1] < tw:
            return None
        score = cv2.matchTemplate(white, text, cv2.TM_CCORR_NORMED)
        score = np.nan_to_num(score, nan=0.0)
        ys, xs = np.nonzero(score >= 0.75)
        if len(ys) == 0:
            return None
        d = np.hypot(xs + tw / 2 - ref[0], ys - ref[1])
        i = int(np.argmin(d - 200 * score[ys, xs]))  # good and near
        return int(xs[i]), int(ys[i]), tw, th, float(score[ys[i], xs[i]])

    def read(
        self, frame: np.ndarray, mm_world: tuple[float, float] | None
    ) -> WorldEstimate:
        t0 = time.perf_counter()
        h, w = frame.shape[:2]
        scaled = w > PLAY_WIDTH
        scale = w / PLAY_WIDTH if scaled else 1.0
        play = (
            cv2.resize(
                frame, (PLAY_WIDTH, round(h / scale)), interpolation=cv2.INTER_AREA
            )
            if scaled
            else frame
        )
        if scaled:
            cam, conf, how = self._camera_scaled(play, mm_world)
        else:
            cam, conf, how = self._camera_exact(play, mm_world)
        t1 = time.perf_counter()
        vx, vy = self.a.origin
        if cam is None:
            self.last_cam = None
            return WorldEstimate(
                False, how, scale=scale, ms=(t1 - t0) * 1e3, ms_camera=(t1 - t0) * 1e3
            )
        self.last_cam = cam
        camera = (cam[0] + vx, cam[1] + vy)
        # Where to look for the character, on the captured frame.
        guess = None
        if mm_world is not None:
            guess = (
                (mm_world[0] - camera[0]) * scale,
                (mm_world[1] - camera[1]) * scale,
            )
        elif self.last_feet is not None:
            guess = (
                (self.last_feet[0] - camera[0]) * scale,
                (self.last_feet[1] - camera[1]) * scale,
            )
        feet, box, cconf, chow = self._feet(frame, scale, guess, mm_world is not None)
        ms = (time.perf_counter() - t0) * 1e3
        est = WorldEstimate(
            False,
            chow,
            camera,
            conf,
            how,
            scale,
            feet,
            box,
            cconf,
            chow,
            None,
            ms,
            (t1 - t0) * 1e3,
        )
        if feet is None:
            est.status = f"camera ok, character not found ({chow})"
            return est
        est.world = (camera[0] + feet[0] / scale, camera[1] + feet[1] / scale)
        est.ok, est.status = True, "read"
        self.last_feet = est.world
        return est


def _ncc_locate(
    static: np.ndarray,
    play: np.ndarray,
    seed: tuple[int, int],
    radius: int,
    scale: int = 4,
    fine: int = 6,
    grid: int = 3,
) -> tuple[tuple[int, int], float]:
    """
    The camera (render px) near `seed`, and its score: the render's crop at the
    seed, shrunk by `radius` on every side, cut into `grid` x `grid` tiles, each
    slid over the frame (masked by its alpha, normalised correlation), coarse
    at 1/`scale` then at full resolution. A displacement scores the mean of its
    best half of the tiles, so a window covering a few tiles doesn't sink it.
    """
    h, w = play.shape[:2]
    radius = min(radius, h // 3, w // 3) // scale * scale
    x0, y0 = seed[0] - radius, seed[1] - radius
    win = np.zeros((h + 2 * radius, w + 2 * radius, 4), np.uint8)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1 = min(static.shape[1], x0 + w + 2 * radius)
    sy1 = min(static.shape[0], y0 + h + 2 * radius)
    if sx1 > sx0 and sy1 > sy0:
        win[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = static[sy0:sy1, sx0:sx1]
    tt = win[2 * radius : h, 2 * radius : w]
    tg = cv2.cvtColor(np.ascontiguousarray(tt[:, :, :3]), cv2.COLOR_RGB2GRAY).astype(
        np.float32
    )
    ta = (tt[:, :, 3] >= 128).astype(np.float32)
    fg = cv2.cvtColor(play, cv2.COLOR_BGR2GRAY).astype(np.float32)

    def small(im: np.ndarray) -> np.ndarray:
        return cv2.resize(
            im, None, fx=1 / scale, fy=1 / scale, interpolation=cv2.INTER_AREA
        )

    def combined(
        img: np.ndarray,
        tmpl: np.ndarray,
        mask: np.ndarray,
        span: int,
        at: tuple[int, int],
    ) -> np.ndarray | None:
        """Per displacement in [0, span], the mean of the best half of the
        tiles' scores; `at` shifts every tile's search window."""
        th, tw = tmpl.shape
        maps = []
        for gy in range(grid):
            for gx in range(grid):
                ty0, ty1 = th * gy // grid, th * (gy + 1) // grid
                tx0, tx1 = tw * gx // grid, tw * (gx + 1) // grid
                m = mask[ty0:ty1, tx0:tx1]
                if m.mean() < 0.2 or m.sum() < 50:
                    continue
                iy, ix = ty0 + at[1], tx0 + at[0]
                region = img[iy : iy + (ty1 - ty0) + span, ix : ix + (tx1 - tx0) + span]
                if (
                    region.shape[0] < (ty1 - ty0) + span
                    or region.shape[1] < (tx1 - tx0) + span
                ):
                    continue
                r = cv2.matchTemplate(
                    region, tmpl[ty0:ty1, tx0:tx1], cv2.TM_CCORR_NORMED, mask=m
                )
                maps.append(
                    np.nan_to_num(
                        r[: span + 1, : span + 1], nan=-1, posinf=-1, neginf=-1
                    )
                )
        if len(maps) < 3:
            return None
        stack = np.sort(np.stack(maps), axis=0)[::-1]
        return stack[: max(3, (len(maps) + 1) // 2)].mean(axis=0)

    coarse = combined(small(fg), small(tg), small(ta), 2 * radius // scale, (0, 0))
    if coarse is None:
        return seed, 0.0
    j, i = np.unravel_index(int(np.argmax(coarse)), coarse.shape)
    dx = min(max(int(i) * scale - fine, 0), 2 * radius - 2 * fine)
    dy = min(max(int(j) * scale - fine, 0), 2 * radius - 2 * fine)
    found = combined(fg, tg, ta, 2 * fine, (dx, dy))
    if found is None:
        return seed, 0.0
    j, i = np.unravel_index(int(np.argmax(found)), found.shape)
    loc_x, loc_y = dx + int(i), dy + int(j)  # displacement of the crop in the frame
    # The crop is the render at seed + radius, found at frame loc: camera = seed + radius - loc.
    return (seed[0] + radius - loc_x, seed[1] + radius - loc_y), float(found[j, i])


def _white(scale: float) -> int:
    return 245 if scale == 1.0 else 190


def _dark(scale: float) -> int:
    return 90 if scale == 1.0 else 110


@dataclass(frozen=True)
class Tag:
    """A name tag's text box (widened by the joining), and how dark around it."""

    x: int
    y: int
    w: int
    h: int
    dark: float


def find_name_tags(region: np.ndarray, scale: float = 1.0) -> list[Tag]:
    """
    Name tags in `region`: white text on a dark box, letters joined across
    small gaps. At 1:1 the text is 255 and the box 90 or less on every channel (it is translucent);
    an upscaled client blurs both (`_white`, `_dark`).
    """
    lightest = region.min(axis=2)
    white = (lightest >= _white(scale)).astype(np.uint8)
    dark = region.max(axis=2) <= _dark(scale)
    joined = cv2.dilate(white, np.ones((1, max(3, round(7 * scale))), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out: list[Tag] = []
    rh, rw = region.shape[:2]
    for x, y, w, h, _ in stats[1:]:
        if not (6 * scale <= h <= 16 * scale and 12 * scale <= w <= 220 * scale):
            continue
        y0, y1 = max(0, y - 2), min(rh, y + h + 2)
        x0, x1 = max(0, x - 2), min(rw, x + w + 2)
        box_white = white[y0:y1, x0:x1].astype(bool)
        # Upscaling smears the text's edges into mid greys: not the box either.
        bg = ~box_white & (lightest[y0:y1, x0:x1] < (245 if scale == 1.0 else 120))
        if bg.sum() == 0 or box_white.sum() < 6 * scale:
            continue
        conf = float(dark[y0:y1, x0:x1][bg].mean())
        if conf < 0.75:
            continue
        out.append(Tag(int(x), int(y), int(w), int(h), conf))
    return out


# ------------------------------------------------------------------------- fusion


@dataclass
class Fused:
    status: str  # agree | DISAGREE | minimap only | world only | unsure
    world: tuple[float, float] | None
    dx: float | None = None
    dy: float | None = None
    dist: float | None = None  # the residual below, in virtual px
    residual: tuple[int, int] | None = None  # canvas px: read minus predicted


def fuse(mm: MinimapEstimate, wd: WorldEstimate, data: MapData) -> Fused:
    """
    Both read: the canvas pixel the world position predicts for the marker
    (`MARKER_ROWS_ABOVE`) against the one read; within one pixel on each axis
    they agree, and the world position is kept, being the finer. One read: it.
    """
    if mm.ok and wd.ok:
        assert mm.canvas_pos is not None
        assert wd.world is not None
        assert mm.world is not None
        m = data.minimap
        assert m is not None
        k = 2**m.mag
        ex = math.floor((wd.world[0] + m.center_x) / k)
        ey = math.floor((wd.world[1] + m.center_y) / k) - MARKER_ROWS_ABOVE
        rx, ry = mm.canvas_pos[0] - ex, mm.canvas_pos[1] - ey
        dx, dy = mm.world[0] - wd.world[0], mm.world[1] - wd.world[1]
        dist = k * math.hypot(rx, ry)
        if abs(rx) <= 1 and abs(ry) <= 1:
            return Fused("agree", wd.world, dx, dy, dist, (rx, ry))
        return Fused("DISAGREE", None, dx, dy, dist, (rx, ry))
    if wd.ok:
        return Fused("world only", wd.world)
    if mm.ok:
        return Fused("minimap only", mm.feet)
    return Fused("unsure", None)


# ------------------------------------------------------------------------ sources


def frames_from_dir(folder: Path, pattern: str) -> Iterator[tuple[str, np.ndarray]]:
    for path in sorted(folder.glob(pattern)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is not None:
            yield path.name, image


def frames_live() -> Iterator[tuple[str, np.ndarray]]:
    from botting.screen import frame_source
    from maple.screen.client import find_client

    handle = find_client()
    source = frame_source()
    n = 0
    while True:
        frame = source.grab(handle)
        if frame.pixels.size == 0 or (not frame.ok and "in front" not in frame.reason):
            # Blank, or not the client's pixels for a reason other than focus.
            time.sleep(0.05)
            continue
        if not frame.fresh:
            time.sleep(0.005)
            continue
        n += 1
        yield f"live {n}{'' if frame.ok else ' (not in front)'}", frame.pixels


# ------------------------------------------------------------------------- viewer

MM_COLOUR = (255, 200, 0)  # BGR: light blue
WD_COLOUR = (0, 220, 0)
FU_COLOUR = (255, 0, 255)


class Viewer:
    def __init__(self, assets: MapAssets, height: int, trail: int) -> None:
        self.a = assets
        full = assets.full
        self.s = min(height / full.shape[0], 1100 / full.shape[1], 1.0)
        self.base = cv2.resize(
            full, None, fx=self.s, fy=self.s, interpolation=cv2.INTER_AREA
        )
        self.trails = {k: collections.deque(maxlen=trail) for k in ("fu", "wd", "mm")}
        self.paused = False

    def _to_view(self, p: tuple[float, float]) -> tuple[int, int]:
        vx, vy = self.a.origin
        return int((p[0] - vx) * self.s), int((p[1] - vy) * self.s)

    def draw(
        self,
        name: str,
        frame: np.ndarray,
        mm: MinimapEstimate,
        wd: WorldEstimate,
        fu: Fused,
        fps: float,
    ) -> int:
        """Shows the picture; the key pressed in this window, if any."""
        cv2.imshow(
            "hybrid tracker (capture only)", self.compose(name, frame, mm, wd, fu, fps)
        )
        return cv2.waitKey(1) & 0xFF

    def compose(
        self,
        name: str,
        frame: np.ndarray,
        mm: MinimapEstimate,
        wd: WorldEstimate,
        fu: Fused,
        fps: float,
    ) -> np.ndarray:
        for k, p in (
            ("mm", mm.world if mm.ok else None),
            ("wd", wd.world if wd.ok else None),
            ("fu", fu.world),
        ):
            if p is not None:
                self.trails[k].append(p)
        view = self.base.copy()
        if wd.camera is not None:
            ph, pw = frame.shape[0] / wd.scale, frame.shape[1] / wd.scale
            a = self._to_view(wd.camera)
            b = self._to_view((wd.camera[0] + pw, wd.camera[1] + ph))
            cv2.rectangle(view, a, b, (200, 200, 200), 1)
        colours = {"mm": MM_COLOUR, "wd": WD_COLOUR, "fu": FU_COLOUR}
        for k, trail in self.trails.items():
            pts = np.array([self._to_view(p) for p in trail], np.int32)
            if len(pts) > 1:
                cv2.polylines(view, [pts], False, colours[k], 1, cv2.LINE_AA)
        self._markers(view, mm, wd, fu, self._to_view, 6)
        zoom = self._zoom(mm, wd, fu)
        thumb = self._thumb(frame, mm, wd)
        panel_w = max(zoom.shape[1], thumb.shape[1])
        text = self._text(name, mm, wd, fu, fps, panel_w)
        right = _vstack([thumb, zoom, text], panel_w)
        left = view
        h = max(left.shape[0], right.shape[0])
        out = np.zeros((h, left.shape[1] + right.shape[1] + 4, 3), np.uint8)
        out[: left.shape[0], : left.shape[1]] = left
        out[: right.shape[0], left.shape[1] + 4 :] = right
        return out

    def _markers(
        self,
        img: np.ndarray,
        mm: MinimapEstimate,
        wd: WorldEstimate,
        fu: Fused,
        to: Any,
        r: int,
    ) -> None:
        if mm.ok and mm.world is not None:
            # Ring: the marker as #365 converts it; dot and line: the feet it
            # implies once MARKER_ROWS_ABOVE is undone.
            cv2.circle(img, to(mm.world), r, MM_COLOUR, 2)
            if mm.feet is not None:
                cv2.line(img, to(mm.world), to(mm.feet), MM_COLOUR, 1)
                cv2.circle(img, to(mm.feet), 3, MM_COLOUR, -1)
        if wd.ok and wd.world is not None:
            p = to(wd.world)
            cv2.drawMarker(img, p, WD_COLOUR, cv2.MARKER_CROSS, 2 * r + 4, 2)
        if fu.world is not None:
            p = to(fu.world)
            cv2.rectangle(img, (p[0] - r, p[1] - r), (p[0] + r, p[1] + r), FU_COLOUR, 2)

    def _zoom(self, mm: MinimapEstimate, wd: WorldEstimate, fu: Fused) -> np.ndarray:
        """The map at 1:1 around the estimate, where 16 px is visible."""
        zw, zh = 420, 300
        centre = fu.world or wd.world or mm.world
        img = np.zeros((zh, zw, 3), np.uint8)
        if centre is None:
            return img
        vx, vy = self.a.origin
        cx, cy = int(centre[0] - vx), int(centre[1] - vy)
        full = self.a.full
        x0, y0 = cx - zw // 2, cy - zh // 2
        sx0, sy0 = max(0, x0), max(0, y0)
        sx1, sy1 = min(full.shape[1], x0 + zw), min(full.shape[0], y0 + zh)
        if sx1 > sx0 and sy1 > sy0:
            img[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = full[sy0:sy1, sx0:sx1]
        for fh in self.a.data.footholds:
            a = (fh.x1 - vx - x0, fh.y1 - vy - y0)
            b = (fh.x2 - vx - x0, fh.y2 - vy - y0)
            cv2.line(img, a, b, (255, 255, 255), 1)

        def to(p: tuple[float, float]) -> tuple[int, int]:
            return int(p[0] - vx - x0), int(p[1] - vy - y0)

        self._markers(img, mm, wd, fu, to, 7)
        cv2.putText(
            img,
            "1:1 zoom, white = footholds",
            (4, zh - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )
        return img

    def _thumb(
        self, frame: np.ndarray, mm: MinimapEstimate, wd: WorldEstimate
    ) -> np.ndarray:
        img = frame.copy()
        if mm.area is not None:
            x0, y0, x1, y1 = mm.area
            cv2.rectangle(img, (x0, y0), (x1, y1), MM_COLOUR, 2)
        if wd.tag_box is not None:
            x0, y0, x1, y1 = wd.tag_box
            cv2.rectangle(img, (x0, y0), (x1, y1), WD_COLOUR, 2)
        if wd.feet_screen is not None:
            cv2.drawMarker(
                img,
                (int(wd.feet_screen[0]), int(wd.feet_screen[1])),
                WD_COLOUR,
                cv2.MARKER_CROSS,
                16,
                2,
            )
        s = 420 / img.shape[1]
        return cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)

    def _text(
        self,
        name: str,
        mm: MinimapEstimate,
        wd: WorldEstimate,
        fu: Fused,
        fps: float,
        width: int,
    ) -> np.ndarray:
        def pt(p: tuple[float, float] | None) -> str:
            return "-" if p is None else f"({p[0]:.0f}, {p[1]:.0f})"

        lines = [
            (f"{name}   {fps:.1f} fps", (255, 255, 255)),
            (
                f"MINIMAP {pt(mm.world) if mm.ok else 'UNSURE'}  canvas {mm.canvas_pos}",
                MM_COLOUR,
            ),
            (f"  {mm.status}; canvas drawn {mm.share:.0%}; {mm.ms:.1f} ms", MM_COLOUR),
            (
                f"WORLD   {pt(wd.world) if wd.ok else 'UNSURE'}  camera {pt(wd.camera)}",
                WD_COLOUR,
            ),
            (
                f"  {wd.camera_method} conf {wd.camera_conf:.2f}; {wd.char_method} {wd.char_conf:.2f}",
                WD_COLOUR,
            ),
            (f"  {wd.status}; {wd.ms:.1f} ms (camera {wd.ms_camera:.1f})", WD_COLOUR),
            (f"FUSED   {fu.status} {pt(fu.world)}", FU_COLOUR),
        ]
        if fu.dist is not None:
            lines.append(
                (
                    (
                        f"  minimap - world: dx {fu.dx:+.0f} dy {fu.dy:+.0f} px; "
                        f"vs predicted marker {fu.residual} canvas px"
                    ),
                    FU_COLOUR,
                )
            )
        lines.append(("q quit, space pause, c clear trails", (160, 160, 160)))
        img = np.zeros((18 * len(lines) + 8, width, 3), np.uint8)
        for i, (t, c) in enumerate(lines):
            cv2.putText(
                img,
                t,
                (4, 16 + 18 * i),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                c,
                1,
                cv2.LINE_AA,
            )
        return img


def _vstack(parts: list[np.ndarray], width: int) -> np.ndarray:
    h = sum(p.shape[0] for p in parts) + 4 * len(parts)
    out = np.zeros((h, width, 3), np.uint8)
    y = 0
    for p in parts:
        out[y : y + p.shape[0], : p.shape[1]] = p
        y += p.shape[0] + 4
    return out


# --------------------------------------------------------------------------- main

CSV_FIELDS = [
    "time", "frame", "mm_ok", "mm_status", "mm_x", "mm_y", "mm_canvas_x", "mm_canvas_y",
    "mm_share", "wd_ok", "wd_status", "wd_x", "wd_y", "camera_x", "camera_y", "camera_conf",
    "camera_method", "char_method", "char_conf", "fused_status", "fused_x", "fused_y",
    "dx", "dy", "dist", "ms_minimap", "ms_world",
]  # fmt: skip


def _row(
    t: float, name: str, mm: MinimapEstimate, wd: WorldEstimate, fu: Fused
) -> dict[str, Any]:
    def c(p: tuple[float, float] | None, i: int) -> str:
        return "" if p is None else f"{p[i]:.1f}"

    return {
        "time": f"{t:.3f}", "frame": name, "mm_ok": int(mm.ok), "mm_status": mm.status,
        "mm_x": c(mm.world, 0), "mm_y": c(mm.world, 1),
        "mm_canvas_x": "" if mm.canvas_pos is None else mm.canvas_pos[0],
        "mm_canvas_y": "" if mm.canvas_pos is None else mm.canvas_pos[1],
        "mm_share": f"{mm.share:.3f}", "wd_ok": int(wd.ok), "wd_status": wd.status,
        "wd_x": c(wd.world, 0), "wd_y": c(wd.world, 1),
        "camera_x": c(wd.camera, 0), "camera_y": c(wd.camera, 1),  # type: ignore[arg-type]
        "camera_conf": f"{wd.camera_conf:.3f}", "camera_method": wd.camera_method,
        "char_method": wd.char_method, "char_conf": f"{wd.char_conf:.3f}",
        "fused_status": fu.status, "fused_x": c(fu.world, 0), "fused_y": c(fu.world, 1),
        "dx": "" if fu.dx is None else f"{fu.dx:.1f}", "dy": "" if fu.dy is None else f"{fu.dy:.1f}",
        "dist": "" if fu.dist is None else f"{fu.dist:.1f}",
        "ms_minimap": f"{mm.ms:.2f}", "ms_world": f"{wd.ms:.2f}",
    }  # fmt: skip


def summary(rows: list[dict[str, Any]]) -> str:
    n = len(rows)
    if n == 0:
        return "no frames"

    def pct(k: str, v: Any = 1) -> str:
        m = sum(1 for r in rows if r[k] == v)
        return f"{m}/{n} ({m / n:.0%})"

    cam = sum(1 for r in rows if r["camera_x"] != "")
    fused = collections.Counter(r["fused_status"] for r in rows)
    out = [
        f"frames: {n}",
        f"minimap read: {pct('mm_ok')}; camera found: {cam}/{n}; world read: {pct('wd_ok')}",
        "fused: " + ", ".join(f"{k} {v}" for k, v in fused.most_common()),
    ]
    both = [r for r in rows if r["dx"] != ""]
    if both:
        dx = np.array([float(r["dx"]) for r in both])
        dy = np.array([float(r["dy"]) for r in both])
        d = np.array([float(r["dist"]) for r in both])
        q = lambda a: " / ".join(f"{v:.0f}" for v in np.percentile(a, [10, 50, 90]))  # noqa: E731
        out += [
            f"both read: {len(both)}; minimap - world (p10 / median / p90):",
            f"  dx {q(dx)}; dy {q(dy)}; marker vs predicted from world {q(d)} virtual px",
        ]
    ms_mm = np.array([float(r["ms_minimap"]) for r in rows])
    ms_wd = np.array([float(r["ms_world"]) for r in rows])
    out.append(
        f"time per frame, median (p90): minimap {np.median(ms_mm):.1f} ({np.percentile(ms_mm, 90):.1f}) ms, "
        f"world {np.median(ms_wd):.1f} ({np.percentile(ms_wd, 90):.1f}) ms"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0] if __doc__ else None
    )
    p.add_argument(
        "--map", required=True, help="map ID or unique name (game_data's rules)"
    )
    p.add_argument(
        "--frames",
        type=Path,
        help="replay PNG frames from this folder instead of capturing",
    )
    p.add_argument(
        "--glob", default="*.png", help="which frames in --frames (default *.png)"
    )
    p.add_argument(
        "--store", type=Path, default=STORE, help=f"game_data store (default {STORE})"
    )
    p.add_argument(
        "--cache",
        type=Path,
        default=REPO / "data" / "poc_tracking",
        help="where renders are cached",
    )
    p.add_argument(
        "--weights",
        type=Path,
        default=MODEL,
        help="YOLO weights; the name-tag finder when absent",
    )
    p.add_argument(
        "--log", type=Path, help="write every frame's three estimates to this CSV"
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="no window: print a line per frame and a summary",
    )
    p.add_argument("--trail", type=int, default=300)
    p.add_argument("--view-height", type=int, default=760)
    args = p.parse_args(argv)

    assets = load_assets(args.store, args.map, args.cache)
    minimap = MinimapTracker(assets)
    if not args.frames:
        minimap.search_cooldown = 0.5
    world = WorldTracker(assets, args.weights)
    viewer = None if args.headless else Viewer(assets, args.view_height, args.trail)
    source = frames_from_dir(args.frames, args.glob) if args.frames else frames_live()
    rows: list[dict[str, Any]] = []
    writer = None
    log = open(args.log, "w", newline="") if args.log else None  # noqa: SIM115
    if log:
        writer = csv.DictWriter(log, CSV_FIELDS)
        writer.writeheader()
    t_start, last = time.perf_counter(), time.perf_counter()
    fps = 0.0
    try:
        for name, frame in source:
            mm = minimap.read(frame)
            wd = world.read(frame, mm.feet if mm.ok else None)
            fu = fuse(mm, wd, assets.data)
            now = time.perf_counter()
            fps = (
                0.8 * fps + 0.2 / max(now - last, 1e-6)
                if fps
                else 1 / max(now - last, 1e-6)
            )
            last = now
            row = _row(now - t_start, name, mm, wd, fu)
            rows.append(row)
            if writer:
                writer.writerow(row)
            if viewer is None:
                print(
                    f"{name:36s} mm {row['mm_x']:>7s},{row['mm_y']:>7s} "
                    f"wd {row['wd_x']:>7s},{row['wd_y']:>7s} cam {row['camera_x']:>6s},{row['camera_y']:>6s} "
                    f"{fu.status:12s} dy {row['dy']:>6s} | {mm.status[:22]} | {wd.status[:40]}"
                )
                continue
            wait = args.delay if args.frames else 1
            key = viewer.draw(name, frame, mm, wd, fu, fps)
            t_end = time.perf_counter() + wait / 1000
            while key not in (ord("q"), 27) and (
                viewer.paused or time.perf_counter() < t_end
            ):
                if key == ord(" "):
                    viewer.paused = not viewer.paused
                if key == ord("c"):
                    for t in viewer.trails.values():
                        t.clear()
                    world.tag_text = None  # learn the name tag again
                    world.tag_widths.clear()
                key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if log:
            log.close()
        cv2.destroyAllWindows()
    print(summary(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
