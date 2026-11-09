"""
POC: the character's position in virtual (world) coordinates, read from the
play area.

**Capture only. This script never sends a key, a click or any other input to
the game.** It copies the client's pixels (Desktop Duplication, through
`botting.screen.frame_source`) and draws its own OpenCV window; the only keys it
reads are the ones pressed in that window (`q` or Esc to quit, space to pause a
replay).

Each frame:

1. **Camera.** The map's static layers (tiles, objects, and the backgrounds
   fixed to the map) are rendered once from `game_data`, and the client draws
   them pixel for pixel. Exact-colour voting (a Hough transform on RGB) finds
   the camera's top-left: seeded by the last camera first, then over the
   whole map (2 to 3 ms either way). The answer is accepted only if the share
   of the render's opaque pixels drawn exactly there passes, and is a sharp
   peak against its 8 neighbours; otherwise the camera is UNSURE and no number
   is given. Clients above 1366x768 (1920x1080) draw the play area at 1366x768
   and upscale it bilinearly, which destroys exact colours: there, a coarse
   masked NCC proposes cameras, and the share of pixels within a tolerance of
   the render upscaled the same way picks and checks one.
2. **Character.** The production YOLO weights don't find the character on
   MSCW frames, so this uses its **name tag**: white text on the plain tag's
   dark translucent box, drawn just under the feet. Several players (and pets)
   have tags; the bot's own is the one nearest the minimap's position for it,
   else nearest the last position, else nearest the screen's centre column.
3. **World position** = camera + feet on screen, in virtual coordinates.
4. **Minimap**, for comparison: `maple.screen.minimap.MinimapReader`'s marker,
   moved from the map area onto the map's minimap canvas (which the area
   centres or scrolls), then `canvas * 2**mag - centre`. A simple read: the
   sibling minimap POC does it properly.

Usage:
    python toolkit/poc_tracking/world_tracker.py --map "Damp Forest"
    python toolkit/poc_tracking/world_tracker.py --map 10005031 --frames DIR
    python toolkit/poc_tracking/world_tracker.py --map 10005031 --frames DIR \
        --labels tests/frames/v2.json --no-window      # offline evaluation

See `world_tracker.md` beside this file.
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
from typing import Any

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game_data.catalogue import Catalogue, MapData
from game_data.config import STORE
from game_data.render import Images, render_map

CACHE = ROOT / "data" / "poc_tracking"

# The play area is drawn at most this big; larger clients upscale it.
NATIVE_PLAY = (1366, 768)

# Exact-colour voting.
MAX_OCCURRENCES = 64  # colours drawn more often than this in the render don't vote
GLOBAL_SAMPLES = 3000
SEEDED_SAMPLES = 1500
SEED_RADIUS = 160  # px around the last camera
SEED_MAX_AGE_S = 2.0
CAMERA_MARGIN = 16  # px the camera may stray outside the VR bounds

# The confidence gate (exact share of the render's opaque pixels in view).
SHARE_SAMPLES = 6000
MIN_SHARE = 0.15
MIN_PEAK_RATIO = 1.5  # share at the answer / best share at its 8 neighbours
MIN_OPAQUE_SAMPLES = 150
# Scaled clients: the share of sampled pixels near the render upscaled
# bilinearly, at the answer and against its 8 neighbours.
COARSE = 8  # the masked NCC that proposes cameras runs at 1/COARSE
COARSE_CANDIDATES = 6
SEEDED_REACH = 12  # px searched around the last camera
NEAR_SAMPLES = 2000
NEAR_TOLERANCE = 12  # per channel
MIN_NEAR_SHARE = 0.3
MIN_NEAR_RATIO = 1.2

# The name tag (measured on f010 at 1:1: box 16 rows, text 255, box <= 96).
TAG_GAP = 2  # feet are this many px above the tag's top (game_data.scenes.players)
TAG_TEXT_TOP_TO_BOX = 3  # the box's top is this far above a capital's top

# Picking the own tag.
MINIMAP_DX = 40  # virtual px
MINIMAP_DY = (40, 170)  # feet minus minimap y; the minimap reads ~100 px high
TRACK_DISTANCE = 120
TRACK_MAX_AGE_S = 1.5
TRAIL = 40


# ---------------------------------------------------------------- static map


class _Filtered:
    """A catalogue whose `map_layers` keeps only some items; the rest passes."""

    def __init__(self, cat: Catalogue, keep: Any) -> None:
        self._cat = cat
        self._keep = keep

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cat, name)

    def map_layers(self, map_id: Any) -> tuple[Any, ...]:
        return tuple(it for it in self._cat.map_layers(map_id) if self._keep(it))


def _fixed_back(item: Any) -> bool:
    b = item.background
    return b.rx == -100 and b.ry == -100 and b.type < 4 and b.a == 255


def _static_item(item: Any) -> bool:
    if item.kind == "back":
        return _fixed_back(item)
    return len(item.frames) <= 1


def _moving_item(item: Any) -> bool:
    """Drawn in the map's frame, but not the same from frame to frame."""
    if item.kind == "back":
        b = item.background
        return b.rx == -100 and b.ry == -100 and not _fixed_back(item)
    return len(item.frames) > 1


def static_render(cat: Catalogue, data: MapData, images: Images) -> np.ndarray:
    """
    The map's static layers, RGBA, VR top-left at (0, 0). Pixels that animated
    objects or scrolling fixed backgrounds may cover are made transparent, so
    they never vote. Cached under `data/poc_tracking/`.
    """
    path = CACHE / f"{cat.build}_{data.id}_static.png"
    if path.is_file():
        bgra = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if bgra is not None:
            return cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)
    rgba = render_map(_Filtered(cat, _static_item), data.id, images=images)  # type: ignore[arg-type]
    moving = render_map(_Filtered(cat, _moving_item), data.id, images=images)  # type: ignore[arg-type]
    covered = cv2.dilate(
        (moving[..., 3] > 0).astype(np.uint8), np.ones((9, 9), np.uint8)
    )
    rgba[covered > 0, 3] = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    return rgba


def _keys_rgb(r: np.ndarray, g: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (r.astype(np.int32) << 16) | (g.astype(np.int32) << 8) | b.astype(np.int32)


def _keys_at(frame_bgr: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
    px = frame_bgr[ys, xs]
    return _keys_rgb(px[:, 2], px[:, 1], px[:, 0])


@dataclass
class Registration:
    """One frame's camera, in render pixels (add VR left/top for virtual)."""

    ok: bool
    camera: tuple[int, int] | None
    confidence: float  # exact share (1:1) or near share (scaled)
    peak_ratio: float
    method: str
    ms: float
    detail: str = ""


class StaticMap:
    """The static render, its colour index, and the registration methods."""

    def __init__(self, rgba: np.ndarray) -> None:
        self.rgba = rgba
        self.h, self.w = rgba.shape[:2]
        opaque = rgba[..., 3] == 255
        self.opaque = opaque
        self.key = np.full((self.h, self.w), -1, np.int32)
        self.key[opaque] = _keys_rgb(rgba[..., 0], rgba[..., 1], rgba[..., 2])[opaque]
        ys, xs = np.nonzero(opaque)
        keys = self.key[ys, xs]
        _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
        keep = counts[inverse] <= MAX_OCCURRENCES
        keys, ys, xs = keys[keep], ys[keep], xs[keep]
        order = np.argsort(keys, kind="stable")
        self._ys = ys[order].astype(np.int32)
        self._xs = xs[order].astype(np.int32)
        self._uk, self._start, self._cnt = np.unique(
            keys[order], return_index=True, return_counts=True
        )
        gray = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
        gray[~opaque] = 0
        self.gray = gray
        self._coarse_cache: tuple[np.ndarray, np.ndarray] | None = None

    # ---- camera range

    def camera_range(self, view: tuple[int, int]) -> tuple[int, int, int, int]:
        """x0, y0, x1, y1 (inclusive) the camera's top-left can be at."""
        vw, vh = view
        lo_x, hi_x = sorted((0, self.w - vw))
        lo_y, hi_y = sorted((0, self.h - vh))
        m = CAMERA_MARGIN
        return lo_x - m, lo_y - m, hi_x + m, hi_y + m

    # ---- exact colours (1:1 clients)

    def vote(
        self,
        frame_bgr: np.ndarray,
        samples: int,
        window: tuple[int, int, int, int],
        rng: np.random.Generator,
    ) -> tuple[int, int, int, int]:
        """The camera with most votes in `window` (x0, y0, x1, y1), its votes
        and the runner-up's (3 px or more away)."""
        fh, fw = frame_bgr.shape[:2]
        ys = rng.integers(0, fh, samples)
        xs = rng.integers(0, fw, samples)
        key = _keys_at(frame_bgr, ys, xs)
        i = np.clip(np.searchsorted(self._uk, key), 0, len(self._uk) - 1)
        hit = self._uk[i] == key
        ys, xs, i = ys[hit], xs[hit], i[hit]
        if len(i) == 0:
            return 0, 0, 0, 0
        cnt = self._cnt[i]
        rep = np.repeat(np.arange(len(i)), cnt)
        off = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        idx = self._start[i][rep] + off
        cx = self._xs[idx] - xs[rep]
        cy = self._ys[idx] - ys[rep]
        x0, y0, x1, y1 = window
        w, h = x1 - x0 + 1, y1 - y0 + 1
        cx, cy = cx - x0, cy - y0
        inside = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
        flat = cy[inside] * w + cx[inside]
        if len(flat) == 0:
            return 0, 0, 0, 0
        # Sparse counting: the window can be millions of cameras.
        cams, votes = np.unique(flat, return_counts=True)
        k = int(np.argmax(votes))
        best = int(votes[k])
        bx, by = int(cams[k] % w), int(cams[k] // w)
        far = (np.abs(cams % w - bx) > 2) | (np.abs(cams // w - by) > 2)
        second = int(votes[far].max()) if far.any() else 0
        return bx + x0, by + y0, best, second

    def exact_share(
        self,
        frame_bgr: np.ndarray,
        cam: tuple[int, int],
        sy: np.ndarray,
        sx: np.ndarray,
    ) -> tuple[float, int]:
        """Share of sampled frame pixels over the render's opaque pixels that
        are drawn exactly, with the camera at `cam`; and how many were opaque."""
        my, mx = sy + cam[1], sx + cam[0]
        inside = (mx >= 0) & (mx < self.w) & (my >= 0) & (my < self.h)
        mk = np.full(len(sy), -1, np.int32)
        mk[inside] = self.key[my[inside], mx[inside]]
        opaque = mk >= 0
        n = int(opaque.sum())
        if n == 0:
            return 0.0, 0
        return float(
            (mk[opaque] == _keys_at(frame_bgr, sy[opaque], sx[opaque])).sum()
        ) / n, n

    def check_exact(
        self, keys: np.ndarray, cam: tuple[int, int], rng: np.random.Generator
    ) -> tuple[float, float, int]:
        fh, fw = keys.shape[:2]
        sy = rng.integers(0, fh, SHARE_SAMPLES)
        sx = rng.integers(0, fw, SHARE_SAMPLES)
        share, n = self.exact_share(keys, cam, sy, sx)
        neighbours = [
            self.exact_share(keys, (cam[0] + dx, cam[1] + dy), sy, sx)[0]
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if dx or dy
        ]
        return share, share / max(max(neighbours), 1e-3), n

    def register_exact(
        self,
        frame_bgr: np.ndarray,
        seed: tuple[int, int] | None,
        rng: np.random.Generator,
    ) -> Registration:
        t0 = time.perf_counter()
        keys = frame_bgr
        view = (frame_bgr.shape[1], frame_bgr.shape[0])
        full = self.camera_range(view)
        tried = []
        attempts: list[tuple[str, tuple[int, int, int, int], int]] = []
        if seed is not None:
            r = SEED_RADIUS
            win = (
                max(full[0], seed[0] - r),
                max(full[1], seed[1] - r),
                min(full[2], seed[0] + r),
                min(full[3], seed[1] + r),
            )
            if win[0] <= win[2] and win[1] <= win[3]:
                attempts.append(("seeded vote", win, SEEDED_SAMPLES))
        attempts.append(("global vote", full, GLOBAL_SAMPLES))
        last = None
        for method, win, samples in attempts:
            cx, cy, best, second = self.vote(keys, samples, win, rng)
            if best == 0:
                tried.append(f"{method}: no votes")
                continue
            share, ratio, n = self.check_exact(keys, (cx, cy), rng)
            last = Registration(
                False,
                None,
                share,
                ratio,
                method,
                0.0,
                f"{method}: votes {best}/{second}, share {share:.2f}, peak x{ratio:.1f}, {n} opaque",
            )
            if (
                n >= MIN_OPAQUE_SAMPLES
                and share >= MIN_SHARE
                and ratio >= MIN_PEAK_RATIO
            ):
                ms = (time.perf_counter() - t0) * 1e3
                return Registration(
                    True, (cx, cy), share, ratio, method, ms, last.detail
                )
            tried.append(last.detail)
        ms = (time.perf_counter() - t0) * 1e3
        conf = last.confidence if last else 0.0
        ratio = last.peak_ratio if last else 0.0
        return Registration(False, None, conf, ratio, "exact", ms, "; ".join(tried))

    # ---- scaled clients (resampled play area)

    def bilinear_share(
        self,
        frame_bgr: np.ndarray,
        cam: tuple[int, int],
        xs: np.ndarray,
        ys: np.ndarray,
        scale: tuple[float, float],
    ) -> tuple[float, int]:
        """Share of sampled client pixels within `NEAR_TOLERANCE` of the render
        upscaled bilinearly, as the client upscales its play area, with the
        camera at `cam`; and how many samples fell on opaque render pixels."""
        u = (xs + 0.5) / scale[0] - 0.5 + cam[0]
        v = (ys + 0.5) / scale[1] - 0.5 + cam[1]
        x0 = np.floor(u).astype(np.int32)
        y0 = np.floor(v).astype(np.int32)
        ok = (x0 >= 0) & (x0 + 1 < self.w) & (y0 >= 0) & (y0 + 1 < self.h)
        x0, y0, u, v, xs, ys = x0[ok], y0[ok], u[ok], v[ok], xs[ok], ys[ok]
        op = (
            self.opaque[y0, x0]
            & self.opaque[y0, x0 + 1]
            & self.opaque[y0 + 1, x0]
            & self.opaque[y0 + 1, x0 + 1]
        )
        x0, y0, u, v, xs, ys = x0[op], y0[op], u[op], v[op], xs[op], ys[op]
        n = len(x0)
        if n == 0:
            return 0.0, 0
        fx = (u - x0)[:, None]
        fy = (v - y0)[:, None]
        rgb = self.rgba

        def at(yy: np.ndarray, xx: np.ndarray) -> np.ndarray:
            return rgb[yy, xx, :3].astype(np.float32)

        c = (
            at(y0, x0) * (1 - fx) * (1 - fy)
            + at(y0, x0 + 1) * fx * (1 - fy)
            + at(y0 + 1, x0) * (1 - fx) * fy
            + at(y0 + 1, x0 + 1) * fx * fy
        )
        diff = np.abs(c[:, ::-1] - frame_bgr[ys, xs]).max(axis=1)
        return float((diff <= NEAR_TOLERANCE).mean()), n

    def _coarse(self) -> tuple[np.ndarray, np.ndarray]:
        """The render's gray (centred on 0, transparent at 0) and opacity at
        1/`COARSE`, for the masked correlation."""
        if self._coarse_cache is None:
            f = 1 / COARSE
            gray = cv2.resize(
                self.gray / 255 - 0.5, None, fx=f, fy=f, interpolation=cv2.INTER_AREA
            )
            alpha = cv2.resize(
                self.opaque.astype(np.float32),
                None,
                fx=f,
                fy=f,
                interpolation=cv2.INTER_AREA,
            )
            alpha[alpha < 0.99] = 0  # only wholly opaque cells
            self._coarse_cache = (gray * (alpha > 0), alpha)
        return self._coarse_cache

    def coarse_candidates(
        self, frame_bgr: np.ndarray, view: tuple[int, int], count: int
    ) -> list[tuple[int, int]]:
        """The best `count` cameras by masked NCC at 1/`COARSE` of the frame
        (minus the bottom UI) against the render's opaque pixels."""
        img, mask = self._coarse()
        f = 1 / COARSE
        x0, y0, x1, y1 = self.camera_range(view)
        # The render, padded so every camera in range is a place in it.
        px, py = max(0, -x0) // COARSE + 1, max(0, -y0) // COARSE + 1
        ih, iw = img.shape
        th, tw = round(view[1] * f), round(view[0] * f)
        big = np.zeros((ih + 2 * py + th, iw + 2 * px + tw), np.float32)
        bmask = np.zeros_like(big)
        big[py : py + ih, px : px + iw] = img
        bmask[py : py + ih, px : px + iw] = mask
        play = cv2.resize(frame_bgr, (tw, th), interpolation=cv2.INTER_AREA)
        tmpl = cv2.cvtColor(play, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255 - 0.5
        tmask = np.ones_like(tmpl)
        tmask[int(th * 0.88) :] = 0
        ncc = _masked_ncc(big, bmask, tmpl, tmask)
        # Cameras out of range don't count.
        cams_x = (np.arange(ncc.shape[1]) - px) * COARSE
        cams_y = (np.arange(ncc.shape[0]) - py) * COARSE
        ncc[:, (cams_x < x0 - COARSE) | (cams_x > x1 + COARSE)] = -2
        ncc[(cams_y < y0 - COARSE) | (cams_y > y1 + COARSE), :] = -2
        out = []
        for _ in range(count):
            _, value, _, (lx, ly) = cv2.minMaxLoc(ncc)
            if value <= -1:
                break
            out.append((int(cams_x[lx]), int(cams_y[ly])))
            ncc[max(0, ly - 3) : ly + 4, max(0, lx - 3) : lx + 4] = -2
        return out

    def register_scaled(
        self,
        frame_bgr: np.ndarray,
        view: tuple[int, int],
        seed: tuple[int, int] | None,
        rng: np.random.Generator,
    ) -> Registration:
        """
        A client that upscales its play area (of `view`'s size) to the frame's.

        Candidates (the seed, else the best places by a coarse masked NCC) are
        searched around, and checked, by comparing sampled pixels with the
        render upscaled bilinearly, as the client does: the share within
        `NEAR_TOLERANCE` peaks sharply at the right camera.
        """
        t0 = time.perf_counter()
        fh, fw = frame_bgr.shape[:2]
        scale = (fw / view[0], fh / view[1])
        method = "scaled seeded" if seed is not None else "scaled global"
        if seed is not None:
            candidates = [seed]
            reach = SEEDED_REACH
        else:
            candidates = self.coarse_candidates(frame_bgr, view, COARSE_CANDIDATES)
            reach = COARSE
        sy = rng.integers(0, int(fh * 0.88), NEAR_SAMPLES)
        sx = rng.integers(0, fw, NEAR_SAMPLES)
        scores: dict[tuple[int, int], float] = {}

        def score(c: tuple[int, int]) -> float:
            if c not in scores:
                share, n = self.bilinear_share(frame_bgr, c, sx, sy, scale)
                scores[c] = share if n >= MIN_OPAQUE_SAMPLES else 0.0
            return scores[c]

        best, best_cam = -1.0, (0, 0)
        for cx, cy in candidates:
            # A grid of step 3 (the share's slope reaches about 10 px), then
            # climb in steps of 1.
            here = max(
                (
                    (cx + dx, cy + dy)
                    for dx in range(-reach, reach + 1, 3)
                    for dy in range(-reach, reach + 1, 3)
                ),
                key=score,
            )
            while True:
                step = max(
                    (
                        (here[0] + dx, here[1] + dy)
                        for dx in (-1, 0, 1)
                        for dy in (-1, 0, 1)
                    ),
                    key=score,
                )
                if step == here:
                    break
                here = step
            if score(here) > best:
                best, best_cam = score(here), here
        if best < 0:
            ms = (time.perf_counter() - t0) * 1e3
            return Registration(False, None, 0.0, 0.0, method, ms, "no candidate")
        neighbours = max(
            score((best_cam[0] + dx, best_cam[1] + dy))
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if dx or dy
        )
        ratio = best / max(neighbours, 1e-3)
        ms = (time.perf_counter() - t0) * 1e3
        detail = f"{method}: {len(candidates)} candidates, near share {best:.2f}, peak x{ratio:.2f}"
        ok = best >= MIN_NEAR_SHARE and ratio >= MIN_NEAR_RATIO
        return Registration(
            ok, best_cam if ok else None, best, ratio, method, ms, detail
        )


def _masked_ncc(
    img: np.ndarray, mask: np.ndarray, tmpl: np.ndarray, tmask: np.ndarray
) -> np.ndarray:
    """Zero-mean NCC of `tmpl` at every place in `img`, over the pixels both
    masks keep: six plain correlations, so OpenCV's FFT does the work."""

    def corr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        return cv2.matchTemplate(
            a.astype(np.float32), b.astype(np.float32), cv2.TM_CCORR
        )

    mi = mask * img
    n = corr(mask, tmask)
    s_it = corr(mi, tmask * tmpl)
    s_i = corr(mi, tmask)
    s_ii = corr(mi * img, tmask)
    s_t = corr(mask, tmask * tmpl)
    s_tt = corr(mask, tmask * tmpl * tmpl)
    safe = np.maximum(n, 1.0)
    cov = s_it - s_i * s_t / safe
    var = (s_ii - s_i * s_i / safe) * (s_tt - s_t * s_t / safe)
    out = cov / np.sqrt(np.maximum(var, 1e-9))
    out[n < 0.15 * float(tmask.sum())] = -1  # too little of the render in view
    return out


# ---------------------------------------------------------------- name tags


@dataclass
class Tag:
    """A plain name tag on screen, in the captured frame's pixels."""

    box: tuple[int, int, int, int]  # text x0, y0, x1, y1 (exclusive)
    top: float  # the dark box's top
    feet: tuple[float, float]  # feet, in the frame's pixels
    edge: bool  # whether the box's top was found from its edge


def find_name_tags(bgr: np.ndarray, scale: float = 1.0) -> list[Tag]:
    """
    Plain name tags: white text on a dark translucent box. `scale` is how much
    the play area is upscaled (1 for 1:1 clients).
    """
    s = scale
    white_min = 245 if s == 1.0 else 200
    dark_max = 100 if s == 1.0 else 125
    b, g, r = cv2.split(bgr)  # cv2 reduces channels far faster than numpy
    white = (cv2.min(cv2.min(b, g), r) >= white_min).astype(np.uint8)
    joined = cv2.dilate(white, np.ones((1, 7 if s == 1.0 else round(10 * s)), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    mx = cv2.max(cv2.max(b, g), r)
    fh, fw = mx.shape
    tags: list[Tag] = []
    hs, ws = stats[1:n, cv2.CC_STAT_HEIGHT], stats[1:n, cv2.CC_STAT_WIDTH]
    sized = (
        np.nonzero((hs >= 5 * s) & (hs <= 14 * s) & (ws >= 10 * s) & (ws <= 170 * s))[0]
        + 1
    )
    for i in sized:
        x, y, w, h, _ = (int(v) for v in stats[i])
        px = round(3 * s)
        x0, x1 = max(0, x - px), min(fw, x + w + px)
        y0, y1 = max(0, y - round(2 * s)), min(fh, y + h + round(2 * s))
        region = mx[y0:y1, x0:x1]
        text = white[y0:y1, x0:x1] > 0
        rest = region[~text]
        if rest.size == 0:
            continue
        # The text's own anti-aliasing (scaled) is excluded by a loose cut.
        dark = float((rest <= dark_max).mean())
        if dark < (0.9 if s == 1.0 else 0.7):
            continue
        density = float(text.mean())
        if not ((0.08 if s == 1.0 else 0.03) <= density <= 0.6):
            continue
        top, edge = _box_top(mx, x, x + w, y, s, dark_max)
        cx = x + (w - 1) / 2
        tags.append(Tag((x, y, x + w, y + h), top, (cx, top - TAG_GAP * s), edge))
    return tags


def _box_top(
    mx: np.ndarray, x0: int, x1: int, text_top: int, s: float, dark_max: int
) -> tuple[float, bool]:
    """The tag box's top row: where the brightness drops most, going down,
    just above the text (the box darkens what is behind it to about 37%).
    Falls back on the text's top when the background is too dark to show
    the edge."""
    reach = round(8 * s)
    lo = max(1, text_top - reach)
    if text_top - 1 <= lo:
        return float(text_top - TAG_TEXT_TOP_TO_BOX * s), False
    rows = mx[lo - 1 : text_top, x0:x1].astype(np.float32)
    lit = rows < 200  # leave out the text's own white, should a letter reach up
    means = (rows * lit).sum(axis=1) / np.maximum(lit.sum(axis=1), 1)
    best, best_row = 0.0, -1
    for i in range(1, len(means)):
        above, inside = means[i - 1], means[i]
        if inside <= dark_max * 0.6 and above - inside > 12:
            ratio = (above + 1) / (inside + 1)
            if ratio > best:
                best, best_row = ratio, lo - 1 + i
    if best >= 1.6:
        return float(best_row), True
    return float(text_top - TAG_TEXT_TOP_TO_BOX * s), False


# ---------------------------------------------------------------- minimap


class MinimapPoint:
    """The character's marker on the minimap, in virtual coordinates."""

    def __init__(self, store: Path, build: str, data: MapData) -> None:
        self.error = ""
        self._reader = None
        self._data = data
        if data.minimap is None:
            self.error = "the map has no minimap"
            return
        try:
            from game_data.sprites import Sprites
            from maple.screen.locator import FrameCheck
            from maple.screen.minimap import (
                FRAME_PARTS,
                USER,
                MinimapReader,
                minimap_canvas_path,
            )
            from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

            with Sprites.open(build, store) as sprites:
                canvases = {
                    p: sprites.canvas(p) for p in (*FRAME_PARTS, USER, GAUGE_LABEL)
                }
                canvas = sprites.canvas(minimap_canvas_path(data.id)).rgba
            reader_sprites = ReaderSprites(build, canvases)
            self._reader = MinimapReader(reader_sprites, FrameCheck(reader_sprites))
            # The canvas's opaque pixels, as BGR keys, to find where it is drawn.
            ys, xs = np.nonzero(canvas[..., 3] == 255)
            pick = np.random.default_rng(0).permutation(len(ys))[:1500]
            self._cy, self._cx = ys[pick], xs[pick]
            self._ckey = _keys_rgb(
                canvas[self._cy, self._cx, 0],
                canvas[self._cy, self._cx, 1],
                canvas[self._cy, self._cx, 2],
            )
            self._csize = (canvas.shape[1], canvas.shape[0])
            self._offset: tuple[int, int] | None = None
        except Exception as error:  # a POC: show why, keep tracking
            self.error = f"minimap reader unavailable: {error!r}"

    def read(self, pixels: np.ndarray) -> tuple[float, float] | None:
        if self._reader is None or self._data.minimap is None:
            return None
        from botting.screen import Frame

        h, w = pixels.shape[:2]
        frame = Frame(pixels, (w, h), time.monotonic(), True, True)
        reading = self._reader.read(frame)
        view = reading.value
        if view is None or view.self_position is None:
            return None
        area = view.map_area
        crop = pixels[area.top : area.bottom, area.left : area.right]
        offset = self._canvas_offset(crop)
        if offset is None:
            return None
        cx = view.self_position[0] - offset[0]
        cy = view.self_position[1] - offset[1]
        mm = self._data.minimap
        k = 2**mm.mag
        return cx * k - mm.center_x, cy * k - mm.center_y

    def _canvas_offset(self, crop: np.ndarray) -> tuple[int, int] | None:
        """Where the map's minimap canvas's top-left is in the map area: the
        area is a window on the canvas, centred when narrower, scrolled when
        taller. Exact colours, as `is_expected_map` matches them."""
        ah, aw = crop.shape[:2]
        cw, ch = self._csize
        keys = _keys_rgb(crop[..., 2], crop[..., 1], crop[..., 0])

        def placements(area: int, size: int) -> range:
            if size <= area:  # centred, give or take a pixel of rounding
                c = (area - size) // 2
                return range(c - 1, c + 2)
            return range(area - size, 1)  # scrolled

        candidates = [(x, y) for x in placements(aw, cw) for y in placements(ah, ch)]
        if self._offset in candidates:
            candidates.remove(self._offset)
            candidates.insert(0, self._offset)
        best, best_share = None, 0.0
        for ox, oy in candidates:
            fy, fx = self._cy + oy, self._cx + ox
            inside = (fx >= 0) & (fx < aw) & (fy >= 0) & (fy < ah)
            n = int(inside.sum())
            if n < 100:
                continue
            share = float((keys[fy[inside], fx[inside]] == self._ckey[inside]).mean())
            if share > best_share:
                best, best_share = (ox, oy), share
            if (ox, oy) == self._offset and share >= 0.8:
                break
        if best is None or best_share < 0.6:
            return None
        self._offset = best
        return best


# ---------------------------------------------------------------- tracker


@dataclass
class Result:
    frame_size: tuple[int, int]
    reg: Registration
    camera_world: tuple[int, int] | None = None
    view: tuple[int, int] = (0, 0)  # the play area's size in virtual px
    tags: list[Tag] = field(default_factory=list[Tag])
    own: Tag | None = None
    pick: str = ""
    world: tuple[float, float] | None = None
    minimap: tuple[float, float] | None = None
    total_ms: float = 0.0


class WorldTracker:
    def __init__(
        self, cat: Catalogue, data: MapData, store: Path, use_minimap: bool = True
    ) -> None:
        self.data = data
        images = Images(cat.store.images)
        t = time.perf_counter()
        self.static = StaticMap(static_render(cat, data, images))
        self.setup_s = time.perf_counter() - t
        self.minimap = MinimapPoint(store, cat.build, data) if use_minimap else None
        self.rng = np.random.default_rng(0)
        self._last_cam: tuple[int, int] | None = None
        self._last_cam_at = 0.0
        self._last_world: tuple[float, float] | None = None
        self._last_world_at = 0.0

    def reset(self) -> None:
        self._last_cam = None
        self._last_world = None

    def play_area(self, pixels: np.ndarray) -> tuple[float, tuple[int, int]]:
        """How much the client upscales its play area, and the play area's
        size in virtual px. Clients above 1366x768 draw it at that size and
        upscale it (seen at 1920x1080; other large sizes are unverified)."""
        h, w = pixels.shape[:2]
        if w > NATIVE_PLAY[0] or h > NATIVE_PLAY[1]:
            scale = min(w / NATIVE_PLAY[0], h / NATIVE_PLAY[1])
            return scale, (round(w / scale), round(h / scale))
        return 1.0, (w, h)

    def register(
        self, pixels: np.ndarray, seed: tuple[int, int] | None
    ) -> tuple[Registration, float, tuple[int, int]]:
        scale, view = self.play_area(pixels)
        if scale == 1.0:
            reg = self.static.register_exact(pixels, seed, self.rng)
        else:
            reg = self.static.register_scaled(pixels, view, seed, self.rng)
            if not reg.ok and seed is not None:
                again = self.static.register_scaled(pixels, view, None, self.rng)
                again.ms += reg.ms
                reg = again
        return reg, scale, view

    def step(self, pixels: np.ndarray, now: float | None = None) -> Result:
        now = time.monotonic() if now is None else now
        t0 = time.perf_counter()
        h, w = pixels.shape[:2]
        seed = self._last_cam if now - self._last_cam_at <= SEED_MAX_AGE_S else None
        reg, scale, view = self.register(pixels, seed)
        res = Result((w, h), reg, view=view)
        vr = self.data.vr
        if reg.ok and reg.camera is not None:
            self._last_cam, self._last_cam_at = reg.camera, now
            res.camera_world = (reg.camera[0] + vr.left, reg.camera[1] + vr.top)
        if self.minimap is not None:
            res.minimap = self.minimap.read(pixels)
        res.tags = find_name_tags(pixels, scale)
        if res.camera_world is not None:
            self._pick(res, scale, now)
        res.total_ms = (time.perf_counter() - t0) * 1e3
        return res

    def _to_world(self, res: Result, tag: Tag, scale: float) -> tuple[float, float]:
        assert res.camera_world is not None
        return (
            res.camera_world[0] + tag.feet[0] / scale,
            res.camera_world[1] + tag.feet[1] / scale,
        )

    def _pick(self, res: Result, scale: float, now: float) -> None:
        cands = [(t, self._to_world(res, t, scale)) for t in res.tags]
        chosen = None
        if res.minimap is not None:
            mx, my = res.minimap
            near = [
                (abs(p[0] - mx) + abs(p[1] - my - 100) / 4, t, p)
                for t, p in cands
                if abs(p[0] - mx) <= MINIMAP_DX
                and MINIMAP_DY[0] <= p[1] - my <= MINIMAP_DY[1]
            ]
            if near:
                _, t, p = min(near, key=lambda c: c[0])
                chosen, res.pick = (t, p), "minimap"
            else:
                res.pick = "no tag near the minimap marker"
        elif (
            self._last_world is not None
            and now - self._last_world_at <= TRACK_MAX_AGE_S
        ):
            lx, ly = self._last_world
            near = [(abs(p[0] - lx) + abs(p[1] - ly), t, p) for t, p in cands]
            near = [c for c in near if c[0] <= TRACK_DISTANCE]
            if near:
                _, t, p = min(near, key=lambda c: c[0])
                chosen, res.pick = (t, p), "last position"
            else:
                res.pick = "no tag near the last position"
        elif cands:
            cx = res.frame_size[0] / 2
            t, p = min(cands, key=lambda c: abs(c[0].feet[0] - cx))
            chosen, res.pick = (t, p), "screen centre (unsure: no minimap)"
        else:
            res.pick = "no name tag"
        if chosen is not None:
            res.own, res.world = chosen
            self._last_world, self._last_world_at = chosen[1], now


# ---------------------------------------------------------------- display


class Viewer:
    """The map, downscaled, with the camera, the character and its trail."""

    def __init__(
        self, cat: Catalogue, data: MapData, max_size: tuple[int, int] = (1000, 900)
    ) -> None:
        self.data = data
        vw = data.vr.right - data.vr.left
        vh = data.vr.bottom - data.vr.top
        self.k = min(1.0, max_size[0] / vw, max_size[1] / vh)
        rgba = render_map(cat, data.id, scale=self.k)
        base = np.full((*rgba.shape[:2], 3), 30, np.uint8)
        a = rgba[..., 3:4].astype(np.float32) / 255
        bgr = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2BGR).astype(np.float32)
        self.base = (bgr * a + base * (1 - a)).astype(np.uint8)
        self.trail: deque[tuple[float, float]] = deque(maxlen=TRAIL)
        self.mm_trail: deque[tuple[float, float]] = deque(maxlen=TRAIL)

    def _px(self, wx: float, wy: float) -> tuple[int, int]:
        return (
            round((wx - self.data.vr.left) * self.k),
            round((wy - self.data.vr.top) * self.k),
        )

    def draw(
        self, res: Result, frame: np.ndarray, fps: float, note: str = ""
    ) -> np.ndarray:
        img = self.base.copy()
        reg = res.reg
        if res.world is not None:
            self.trail.append(res.world)
        if res.minimap is not None:
            self.mm_trail.append(res.minimap)
        if res.camera_world is not None:
            x, y = res.camera_world
            cv2.rectangle(
                img,
                self._px(x, y),
                self._px(x + res.view[0], y + res.view[1]),
                (0, 255, 0),
                2,
            )
        for i in range(1, len(self.trail)):
            cv2.line(
                img,
                self._px(*self.trail[i - 1]),
                self._px(*self.trail[i]),
                (0, 0, 200),
                1,
            )
        if res.minimap is not None:
            cv2.circle(img, self._px(*res.minimap), 5, (255, 200, 0), 2)
        if res.world is not None:
            cv2.circle(img, self._px(*res.world), 5, (0, 0, 255), -1)

        # The capture, small, with the tags.
        thumb_w = 420
        k = thumb_w / frame.shape[1]
        thumb = cv2.resize(
            frame, (thumb_w, round(frame.shape[0] * k)), interpolation=cv2.INTER_AREA
        )
        for t in res.tags:
            colour = (0, 0, 255) if t is res.own else (160, 160, 160)
            x0, y0, x1, y1 = t.box
            cv2.rectangle(
                thumb,
                (int(x0 * k) - 2, int(y0 * k) - 2),
                (int(x1 * k) + 2, int(y1 * k) + 2),
                colour,
                1,
            )

        status = "LOCKED" if reg.ok else "UNSURE"
        lines = [
            f"camera: {status} ({reg.method}, conf {reg.confidence:.2f}, peak {reg.peak_ratio:.2f})",
            f"camera world: {res.camera_world if res.camera_world else '-'}",
            "char world: "
            + (f"x={res.world[0]:.0f} y={res.world[1]:.0f}" if res.world else "unsure")
            + f"   [{res.pick}]",
            "minimap world: "
            + (
                f"x={res.minimap[0]:.0f} y={res.minimap[1]:.0f}" if res.minimap else "-"
            ),
            f"client {res.frame_size[0]}x{res.frame_size[1]}  reg {reg.ms:.1f} ms  total {res.total_ms:.1f} ms  {fps:.1f} fps",
            "red: character (name tag)  cyan ring: minimap  green: camera",
        ]
        if note:
            lines.append(note)
        panel_h = max(thumb.shape[0] + 22 * len(lines) + 20, img.shape[0])
        out = np.full((panel_h, img.shape[1] + thumb_w + 10, 3), 20, np.uint8)
        out[: img.shape[0], : img.shape[1]] = img
        ox = img.shape[1] + 10
        out[: thumb.shape[0], ox : ox + thumb_w] = thumb
        y = thumb.shape[0] + 22
        for i, line in enumerate(lines):
            colour = (
                (0, 255, 0)
                if i == 0 and reg.ok
                else (0, 160, 255)
                if i == 0
                else (230, 230, 230)
            )
            cv2.putText(
                out,
                line[:70],
                (ox, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                colour,
                1,
                cv2.LINE_AA,
            )
            y += 22
        return out


# ---------------------------------------------------------------- runs


V2_PREFIXES = {10005031: "f", 10002000: "ghjkm"}  # frame set v2's maps, by file prefix

CSV_FIELDS = [
    "t",
    "source",
    "w",
    "h",
    "status",
    "method",
    "confidence",
    "peak",
    "cam_x",
    "cam_y",
    "char_x",
    "char_y",
    "pick",
    "minimap_x",
    "minimap_y",
    "reg_ms",
    "total_ms",
]


def _row(t: float, source: str, res: Result) -> dict[str, Any]:
    cam = res.camera_world
    return {
        "t": f"{t:.3f}",
        "source": source,
        "w": res.frame_size[0],
        "h": res.frame_size[1],
        "status": "locked" if res.reg.ok else "unsure",
        "method": res.reg.method,
        "confidence": f"{res.reg.confidence:.3f}",
        "peak": f"{res.reg.peak_ratio:.2f}",
        "cam_x": cam[0] if cam else "",
        "cam_y": cam[1] if cam else "",
        "char_x": f"{res.world[0]:.1f}" if res.world else "",
        "char_y": f"{res.world[1]:.1f}" if res.world else "",
        "pick": res.pick,
        "minimap_x": f"{res.minimap[0]:.0f}" if res.minimap else "",
        "minimap_y": f"{res.minimap[1]:.0f}" if res.minimap else "",
        "reg_ms": f"{res.reg.ms:.1f}",
        "total_ms": f"{res.total_ms:.1f}",
    }


def run_live(tracker: WorldTracker, viewer: Viewer, log: Any) -> None:
    from botting.screen import frame_source
    from maple.screen.client import find_client

    handle = find_client()
    source = frame_source()
    cv2.namedWindow("world tracker", cv2.WINDOW_AUTOSIZE)
    last = time.perf_counter()
    fps = 0.0
    start = time.monotonic()
    while True:
        frame = source.grab(handle)
        if frame.pixels.size == 0:
            if cv2.waitKey(200) & 0xFF in (ord("q"), 27):
                break
            continue
        res = tracker.step(frame.pixels, frame.captured_at)
        now = time.perf_counter()
        fps = (
            0.9 * fps + 0.1 / max(now - last, 1e-3)
            if fps
            else 1 / max(now - last, 1e-3)
        )
        last = now
        note = "" if frame.ok else f"capture not trusted: {frame.reason[:60]}"
        cv2.imshow("world tracker", viewer.draw(res, frame.pixels, fps, note))
        if log is not None:
            log.writerow(_row(frame.captured_at - start, "live", res))
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break
    cv2.destroyAllWindows()


def run_frames(
    tracker: WorldTracker, viewer: Viewer | None, folder: Path, delay_ms: int, log: Any
) -> list[tuple[str, Result]]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".png")
    results = []
    paused = False
    t = 0.0
    for i, path in enumerate(files):
        pixels = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if pixels is None:
            continue
        t += 0.1  # replayed frames are treated as 100 ms apart
        res = tracker.step(pixels, t)
        results.append((path.name, res))
        if log is not None:
            log.writerow(_row(t, path.name, res))
        if viewer is not None:
            fps = 1000 / max(res.total_ms, 1e-3)
            cv2.imshow(
                "world tracker",
                viewer.draw(res, pixels, fps, f"{i + 1}/{len(files)} {path.name}"),
            )
            while True:
                key = cv2.waitKey(0 if paused else delay_ms) & 0xFF
                if key in (ord("q"), 27):
                    cv2.destroyAllWindows()
                    return results
                if key == ord(" "):
                    paused = not paused
                    if paused:
                        continue
                break
    if viewer is not None:
        cv2.destroyAllWindows()
    return results


def evaluate(tracker: WorldTracker, folder: Path, labels: Path, cat: Catalogue) -> None:
    """Offline numbers: registration per frame (unseeded and seeded),
    character vs the minimap labels, and the tracking run's timings."""
    data = tracker.data
    names = {f"{data.street}: {data.name}".lower(), (data.name or "").lower()}
    expect: dict[str, tuple[int, int] | None] = {}
    on_map: dict[str, bool] = {}
    for f in json.loads(labels.read_text())["frames"]:
        mm = f["expect"].get("minimap", {})
        value = mm.get("value") or {}
        if value.get("map"):
            on_map[f["file"]] = value["map"].lower() in names
        else:  # unlabelled (covered, minimised): v2's file prefixes name the map
            on_map[f["file"]] = f["file"][0] in V2_PREFIXES.get(data.id, "")
        expect[f["file"]] = (
            tuple(value["self_position"]) if value.get("self_position") else None
        )
    mm = data.minimap
    files = sorted(p for p in folder.iterdir() if p.suffix == ".png")
    rows = []
    for path in files:
        pixels = cv2.imread(str(path), cv2.IMREAD_COLOR)
        assert pixels is not None
        tracker.reset()
        g, scale, _ = tracker.register(pixels, None)
        g2 = None
        if g.ok and g.camera is not None:
            seed = (
                g.camera[0] + 8,
                g.camera[1] - 6,
            )  # about one frame of motion at 10 fps
            g2, _, _ = tracker.register(pixels, seed)
        rows.append((path.name, g, g2, scale))
    # A tracking run in file order, as the live loop runs.
    tracker.reset()
    track = run_frames(tracker, None, folder, 0, None)
    track_by = dict(track)

    def size(n: str) -> str:
        res = track_by[n]
        return f"{res.frame_size[0]}x{res.frame_size[1]}"

    print(f"\nmap {data.id} {data.street}: {data.name}; setup {tracker.setup_s:.1f} s")
    print(
        f"{'frame':38s} {'size':9s} {'unseeded':>30s} {'seeded':>14s}  char world   label world   err"
    )
    stats: dict[str, list[Any]] = {}
    errs = []
    for name, g, g2, _ in rows:
        mine = on_map.get(name, False)
        res = track_by[name]
        bucket = stats.setdefault(
            ("on " if mine else "off ") + size(name), [0, 0, [], [], 0]
        )
        bucket[0] += 1
        bucket[1] += int(g.ok)
        bucket[2].append(g.ms)
        if g2 is not None:
            bucket[3].append(g2.ms)
            bucket[4] += int(g2.ok and g2.camera == g.camera)
        label = expect.get(name)
        lw = None
        if mine and label is not None and mm is not None:
            k = 2**mm.mag
            lw = (label[0] * k - mm.center_x, label[1] * k - mm.center_y)
        err = ""
        if res.world is not None and lw is not None:
            dx, dy = res.world[0] - lw[0], res.world[1] - lw[1]
            errs.append((dx, dy, name))
            err = f"{dx:+.0f},{dy:+.0f}"
        gs = f"{'ok' if g.ok else 'UNSURE'} {g.camera} {g.confidence:.2f} {g.ms:.0f}ms"
        ss = (
            ""
            if g2 is None
            else f"{'ok' if g2.ok and g2.camera == g.camera else 'MISS'} {g2.ms:.1f}ms"
        )
        cw = f"({res.world[0]:.0f},{res.world[1]:.0f})" if res.world else "-"
        lws = f"({lw[0]:.0f},{lw[1]:.0f})" if lw else "-"
        print(
            f"{name[:38]:38s} {size(name):9s} {gs:>30s} {ss:>14s}  {cw:12s} {lws:12s} {err}  [{res.pick}]"
        )
    print(
        "\nregistration by frame group (unseeded accepted / frames; median ms unseeded, seeded; seeded agrees)"
    )
    for key, (n, ok, ms, sms, agree) in sorted(stats.items()):
        med = float(np.median(ms))
        smed = f"{float(np.median(sms)):.1f}" if sms else "-"
        print(f"  {key:16s} {ok}/{n}  {med:.0f} ms  {smed} ms  {agree}/{len(sms)}")
    if errs:
        dx = np.array([e[0] for e in errs])
        dy = np.array([e[1] for e in errs])
        print(
            f"\ncharacter vs minimap label ({len(errs)} frames): "
            f"x median {np.median(dx):+.0f} (|.| median {np.median(np.abs(dx)):.0f}, max {np.abs(dx).max():.0f}); "
            f"y median {np.median(dy):+.0f} (spread {np.percentile(dy, 10):+.0f}..{np.percentile(dy, 90):+.0f})"
        )
    seeded = [
        r.reg.ms
        for _, r in track
        if r.reg.method.startswith(("seeded", "scaled seeded"))
    ]
    total = [r.total_ms for _, r in track]
    print(
        f"tracking run: {sum(r.reg.ok for _, r in track)}/{len(track)} locked, "
        f"{len(seeded)} by the seed; median total {np.median(total):.0f} ms per frame; "
        f"character found on {sum(r.world is not None for _, r in track)}"
    )
    by_size: dict[str, list[float]] = {}
    for name, r in track:
        if on_map.get(name, False):
            by_size.setdefault(size(name), []).append(r.total_ms)
    print(
        "tracking run, this map's frames, median ms per frame (all steps): "
        + ", ".join(f"{k} {np.median(v):.0f}" for k, v in sorted(by_size.items()))
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--map", required=True, help="map id or unique name")
    parser.add_argument(
        "--frames",
        type=Path,
        help="replay the PNGs in this folder instead of capturing",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        help="with --frames: evaluate against these labels (v2.json)",
    )
    parser.add_argument("--delay", type=int, default=400, help="replay: ms per frame")
    parser.add_argument("--no-window", action="store_true")
    parser.add_argument("--no-minimap", action="store_true")
    parser.add_argument("--log", type=Path, help="write one CSV row per frame")
    parser.add_argument(
        "--store", type=Path, default=STORE, help="game_data store root"
    )
    args = parser.parse_args()

    with Catalogue.latest(args.store) as cat:
        data = cat.map(args.map)
        print(
            f"map {data.id} {data.street}: {data.name}; extraction {cat.build}; rendering ..."
        )
        tracker = WorldTracker(cat, data, args.store, not args.no_minimap)
        print(
            f"static render {tracker.static.w}x{tracker.static.h} ready in {tracker.setup_s:.1f} s"
        )
        if tracker.minimap is not None and tracker.minimap.error:
            print(tracker.minimap.error)
        if args.labels is not None:
            if args.frames is None:
                parser.error("--labels needs --frames")
            evaluate(tracker, args.frames, args.labels, cat)
            return
        viewer = None if args.no_window else Viewer(cat, data)
        log_file = None
        writer = None
        if args.log is not None:
            log_file = args.log.open("w", newline="")
            writer = csv.DictWriter(log_file, CSV_FIELDS)
            writer.writeheader()
        try:
            if args.frames is not None:
                for name, res in run_frames(
                    tracker, viewer, args.frames, args.delay, writer
                ):
                    if viewer is None:
                        print(name, _row(0, name, res))
            else:
                if viewer is None:
                    parser.error("live capture needs the window")
                run_live(tracker, viewer, writer)
        finally:
            if log_file is not None:
                log_file.close()


if __name__ == "__main__":
    main()
