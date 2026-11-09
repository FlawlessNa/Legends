"""
The camera: where the play area is on the map (#390, epic #302 Part 2).

A **camera** is the virtual coordinate of the play area's top-left pixel. It
is found by matching the frame against the map's static render
(`WorldMap.static_render`), the art the client draws the same in every frame,
pixel for pixel. This is the world tracking POC's method
(`toolkit/poc_tracking/world_tracker.py` and its `.md`), which labelled the
frame sets' cameras.

**At 1:1 client sizes** (up to `NATIVE_PLAY`), exact-colour voting: every
sampled frame pixel whose colour the render draws in few places
(`MAX_OCCURRENCES`) votes for each camera that would put one of them there.
The camera with most votes is taken, around the seed first (±`SEED_RADIUS`),
then over the whole map. It is accepted when, of `SHARE_SAMPLES` frame pixels
over the render's opaque pixels, at least `MIN_SHARE` are drawn exactly there,
and that share is `MIN_SHARPNESS` times the best at its 8 neighbouring
cameras.

**Above 1:1** the client draws the play area `PLAY_AREA_HEIGHT` high and
upscales it bilinearly, which destroys exact colours. A masked normalised
correlation at 1/`COARSE` proposes `COARSE_CANDIDATES` cameras, or the seed is
the one candidate (searched ±`SEEDED_REACH`). Each is climbed by its **near
share**: the share of sampled frame pixels within `NEAR_TOLERANCE` levels per
channel of the render upscaled bilinearly, as the client upscales it, with the
camera there. The best is accepted at `MIN_NEAR_SHARE`, `MIN_NEAR_SHARPNESS`
times its 8 neighbours. A seed that isn't accepted falls back to the
correlation over the whole map.

**The play area's width above 1:1 is measured, not known.** The client
doesn't say how big it draws the play area. The two whole widths nearest
`PLAY_AREA_HEIGHT` times the client's aspect ratio are both tried at the
camera found, and the one with the higher near share is kept, as
`Camera.play_area`. On frame sets v2 and v3 that is 1366 at 1920x1080 and
2560x1440, and 1228 at 1920x1200 (`tests/frames/README.md`). The height, 768,
is what those frame sets show at every size above 1366x768.

**Never a guess (C-NOGUESS).** A frame that isn't `ok`, and one where no
camera passes both gates, reads `UNSURE`: another map, a frame caught
mid-resize, too little static art in view. Given the bot's `FrameCheck`, as
every screen reader is, a frame it refuses is `UNSURE` too: the static art
can be drawn in a picture that isn't the client's (frame set v2's `f002`, the
desktop over the client), and a client whose UI isn't drawn at 1:1, which
2560x1440 upscales with the rest, is one no other reader can read either. The share and the sharpness are
the evidence, kept in `Camera`; the `Reading` itself carries no confidence.

Pixels are sampled at random, from a generator seeded afresh on every read,
so a frame always reads the same.
"""

import math
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading
from game_data.archive import Pixels
from maple.model.world import WorldMap
from maple.screen.locator import FrameCheck

NATIVE_PLAY: Final = (1366, 768)
"""The largest client the play area is drawn 1:1 in. Seen on frame sets v2
and v3: 1366x768 is 1:1, 1920x1080 isn't."""

PLAY_AREA_HEIGHT: Final = 768
"""How high the play area is drawn on a client above `NATIVE_PLAY`, before
the client upscales it. Seen on frame sets v2 and v3 at 1920x1080, 1920x1200
and 2560x1440."""

CAMERA_MARGIN: Final = 16
"""Pixels the camera may stray outside the VR bounds."""

SAMPLING_SEED: Final = 0
"""Seeds the generator each read samples pixels with."""

# Exact-colour voting, at 1:1.
MAX_OCCURRENCES: Final = 64
"""A colour the render draws more often than this doesn't vote."""
GLOBAL_SAMPLES: Final = 3000
"""Frame pixels that vote when searching the whole map."""
SEEDED_SAMPLES: Final = 1500
"""Frame pixels that vote when searching around the seed."""
SEED_RADIUS: Final = 160
"""Pixels around the seed searched first, at 1:1."""
MIN_DISTINCT_PEAK: Final = 3
"""The runner-up camera reported in a read's detail is at least this far
from the winner, on one axis."""

# The exact gate, at 1:1.
SHARE_SAMPLES: Final = 6000
"""Frame pixels the exact share is counted on."""
MIN_SHARE: Final = 0.15
"""The share of sampled pixels over the render's opaque ones drawn exactly."""
MIN_SHARPNESS: Final = 1.5
"""The share at the camera over the best at its 8 neighbours."""
MIN_OPAQUE_SAMPLES: Final = 150
"""Fewer sampled pixels than this over the render's opaque pixels can't
place the camera, whatever their share."""

# Above 1:1.
COARSE: Final = 8
"""The correlation proposing cameras runs at 1/`COARSE` of the play area."""
COARSE_CANDIDATES: Final = 6
"""Cameras the correlation proposes."""
COARSE_SPACING: Final = 3
"""Coarse cells around a proposal that no other proposal may take."""
MIN_COARSE_COVER: Final = 0.15
"""The share of the play area that must lie on the render's opaque cells for
the correlation to propose a camera."""
SEEDED_REACH: Final = 12
"""Pixels searched around the seed, above 1:1."""
GRID_STEP: Final = 3
"""A candidate is searched on a grid this coarse, then climbed 1 px at a time:
the near share's slope reaches about 10 px."""
NEAR_SAMPLES: Final = 2000
"""Frame pixels the near share is counted on."""
NEAR_TOLERANCE: Final = 12
"""Levels per channel within which a pixel counts as near."""
MIN_NEAR_SHARE: Final = 0.3
"""The near share the camera needs."""
MIN_NEAR_SHARPNESS: Final = 1.2
"""The near share at the camera over the best at its 8 neighbours."""
UI_BAND: Final = 0.12
"""The bottom share of the client, where the status bar is, isn't sampled
above 1:1 (nor used by the correlation)."""

_NEIGHBOURS: Final = tuple(
    (dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy
)

type _Window = tuple[int, int, int, int]
"""Cameras from `(x0, y0)` to `(x1, y1)`, inclusive, in render px."""


@dataclass(frozen=True, slots=True)
class Camera:
    """
    The camera, and how sure the match is.

    :ivar x: The play area's left edge, in virtual px.
    :ivar y: The play area's top edge, in virtual px.
    :ivar share: The exact share at 1:1, the near share above it: how much of
        the static art in view the client draws as the render does there.
    :ivar sharpness: `share` over the best share at the 8 neighbouring
        cameras: how much better this camera is than one pixel off.
    :ivar play_area: The play area's size in virtual px: the client's size at
        1:1, the measured size above it. A pixel of the client is
        `client size / play_area` virtual px wide and high.
    """

    x: int
    y: int
    share: float
    sharpness: float
    play_area: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _Found:
    """A camera in render px, before the gates."""

    x: int
    y: int
    share: float
    sharpness: float
    opaque: int


class CameraReader:
    """
    One map's camera reader. Building it indexes the map's static render
    (drawn and cached on first use, as `StaticRender.pixels` says); reading a
    frame takes a few ms at 1:1, tens to hundreds above it.
    """

    def __init__(
        self,
        world_map: WorldMap,
        *,
        frame_check: FrameCheck | None = None,
        render: Pixels | None = None,
    ) -> None:
        """
        :param world_map: The map whose camera is read.
        :param frame_check: The bot's, asked first; without one, any frame
            that is `ok` is matched.
        :param render: Its static render, RGBA, VR top-left at `(0, 0)`;
            `world_map.static_render`'s pixels when not given.
        :raises ValueError: No render given, and the map has none.
        """
        self._frame_check = frame_check
        if render is None:
            if world_map.static_render is None:
                raise ValueError(f"map {world_map.id} has no static render")
            render = world_map.static_render.pixels()
        self.world_map = world_map
        self._index = _RenderIndex(render)

    def read(self, frame: Frame, seed: Camera | None = None) -> Reading[Camera]:
        """
        The camera in `frame`, or `UNSURE` when it can't be placed.

        :param seed: The last camera read, searched around first; a seed that
            isn't confirmed costs a search over the whole map, never a guess.
        """
        if not frame.ok:
            return Reading.unsure(
                frame.captured_at, f"frame not usable: {frame.reason}"
            )
        if self._frame_check is not None:
            unusable: Reading[Camera] | None = self._frame_check.frame_usable(frame)
            if unusable is not None:
                return unusable
        pixels = frame.pixels
        height, width = pixels.shape[:2]
        rng = np.random.default_rng(SAMPLING_SEED)
        start = time.perf_counter()
        bounds = self.world_map.bounds
        render_seed = (
            None if seed is None else (seed.x - bounds.left, seed.y - bounds.top)
        )
        if width <= NATIVE_PLAY[0] and height <= NATIVE_PLAY[1]:
            found, detail = self._index.register_exact(pixels, render_seed, rng)
            play_area = (width, height)
        else:
            found, play_area, detail = self._index.register_scaled(
                pixels, render_seed, rng
            )
        detail += f" ({(time.perf_counter() - start) * 1e3:.0f} ms)"
        if found is None:
            return Reading.unsure(frame.captured_at, detail)
        camera = Camera(
            found.x + bounds.left,
            found.y + bounds.top,
            found.share,
            found.sharpness,
            play_area,
        )
        return Reading.read(camera, frame.captured_at, detail)


def _keys_rgb(
    red: NDArray[np.uint8], green: NDArray[np.uint8], blue: NDArray[np.uint8]
) -> NDArray[np.int32]:
    return (
        (red.astype(np.int32) << 16)
        | (green.astype(np.int32) << 8)
        | blue.astype(np.int32)
    )


def _keys_at(
    bgr: NDArray[np.uint8], ys: NDArray[np.int64], xs: NDArray[np.int64]
) -> NDArray[np.int32]:
    picked = bgr[ys, xs]
    return _keys_rgb(picked[:, 2], picked[:, 1], picked[:, 0])


def play_area_widths(width: int, height: int) -> tuple[int, ...]:
    """The play area widths tried on a client above `NATIVE_PLAY`: the whole
    numbers either side of `PLAY_AREA_HEIGHT` times its aspect ratio."""
    exact = width * PLAY_AREA_HEIGHT / height
    return tuple(sorted({math.floor(exact), math.ceil(exact)}))


class _RenderIndex:
    """The static render, indexed by colour for voting and kept as gray at
    1/`COARSE` for the correlation."""

    def __init__(self, rgba: Pixels) -> None:
        self.rgb = rgba[..., :3]
        self.height, self.width = rgba.shape[:2]
        self.opaque: NDArray[np.bool_] = rgba[..., 3] == 255
        self.key = np.full((self.height, self.width), -1, np.int32)
        self.key[self.opaque] = _keys_rgb(rgba[..., 0], rgba[..., 1], rgba[..., 2])[
            self.opaque
        ]
        ys, xs = np.nonzero(self.opaque)
        keys = self.key[ys, xs]
        _, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
        rare = counts[inverse] <= MAX_OCCURRENCES
        keys, ys, xs = keys[rare], ys[rare], xs[rare]
        order = np.argsort(keys, kind="stable")
        self._ys = ys[order].astype(np.int32)
        self._xs = xs[order].astype(np.int32)
        self._colours, self._first, self._count = np.unique(
            keys[order], return_index=True, return_counts=True
        )
        self._coarse: tuple[NDArray[np.float32], NDArray[np.float32]] | None = None

    # ---- cameras in range

    def camera_range(self, view: tuple[int, int]) -> _Window:
        """Every camera a play area of `view`'s size can have."""
        lo_x, hi_x = sorted((0, self.width - view[0]))
        lo_y, hi_y = sorted((0, self.height - view[1]))
        margin = CAMERA_MARGIN
        return lo_x - margin, lo_y - margin, hi_x + margin, hi_y + margin

    # ---- 1:1

    def register_exact(
        self,
        bgr: NDArray[np.uint8],
        seed: tuple[int, int] | None,
        rng: np.random.Generator,
    ) -> tuple[_Found | None, str]:
        """The camera by exact-colour voting, around the seed then over the
        whole map, and what was tried."""
        full = self.camera_range((bgr.shape[1], bgr.shape[0]))
        attempts: list[tuple[str, _Window, int]] = []
        if seed is not None:
            window = (
                max(full[0], seed[0] - SEED_RADIUS),
                max(full[1], seed[1] - SEED_RADIUS),
                min(full[2], seed[0] + SEED_RADIUS),
                min(full[3], seed[1] + SEED_RADIUS),
            )
            if window[0] <= window[2] and window[1] <= window[3]:
                attempts.append(("seeded vote", window, SEEDED_SAMPLES))
        attempts.append(("global vote", full, GLOBAL_SAMPLES))
        tried: list[str] = []
        for method, window, samples in attempts:
            voted = self._vote(bgr, samples, window, rng)
            if voted is None:
                tried.append(f"{method}: no votes")
                continue
            x, y, best, second = voted
            found = self._check_exact(bgr, (x, y), rng)
            summary = (
                f"{method}: votes {best}/{second}, share {found.share:.2f}, "
                f"sharpness {found.sharpness:.2f}, {found.opaque} opaque"
            )
            if (
                found.opaque >= MIN_OPAQUE_SAMPLES
                and found.share >= MIN_SHARE
                and found.sharpness >= MIN_SHARPNESS
            ):
                return found, summary
            tried.append(summary)
        return None, "; ".join(tried)

    def _vote(
        self,
        bgr: NDArray[np.uint8],
        samples: int,
        window: _Window,
        rng: np.random.Generator,
    ) -> tuple[int, int, int, int] | None:
        """The camera with most votes in `window`, its votes and the
        runner-up's; `None` when no sample votes there."""
        height, width = bgr.shape[:2]
        ys = rng.integers(0, height, samples)
        xs = rng.integers(0, width, samples)
        keys = _keys_at(bgr, ys, xs)
        at = np.clip(np.searchsorted(self._colours, keys), 0, len(self._colours) - 1)
        hit = self._colours[at] == keys
        ys, xs, at = ys[hit], xs[hit], at[hit]
        if len(at) == 0:
            return None
        count = self._count[at]
        sample = np.repeat(np.arange(len(at)), count)
        offset = np.arange(int(count.sum())) - np.repeat(
            np.cumsum(count) - count, count
        )
        where = self._first[at][sample] + offset
        x0, y0, x1, y1 = window
        span_x, span_y = x1 - x0 + 1, y1 - y0 + 1
        cam_x = self._xs[where] - xs[sample] - x0
        cam_y = self._ys[where] - ys[sample] - y0
        inside = (cam_x >= 0) & (cam_x < span_x) & (cam_y >= 0) & (cam_y < span_y)
        if not inside.any():
            return None
        # Counted sparsely: the window can hold millions of cameras.
        cams, votes = np.unique(
            cam_y[inside].astype(np.int64) * span_x + cam_x[inside], return_counts=True
        )
        k = int(np.argmax(votes))
        best_x, best_y = int(cams[k] % span_x), int(cams[k] // span_x)
        distinct = (np.abs(cams % span_x - best_x) >= MIN_DISTINCT_PEAK) | (
            np.abs(cams // span_x - best_y) >= MIN_DISTINCT_PEAK
        )
        second = int(votes[distinct].max()) if distinct.any() else 0
        return best_x + x0, best_y + y0, int(votes[k]), second

    def _exact_share(
        self,
        bgr: NDArray[np.uint8],
        cam: tuple[int, int],
        ys: NDArray[np.int64],
        xs: NDArray[np.int64],
    ) -> tuple[float, int]:
        """The share of sampled pixels over the render's opaque pixels drawn
        exactly with the camera at `cam`, and how many were over them."""
        ry, rx = ys + cam[1], xs + cam[0]
        inside = (rx >= 0) & (rx < self.width) & (ry >= 0) & (ry < self.height)
        expected = np.full(len(ys), -1, np.int32)
        expected[inside] = self.key[ry[inside], rx[inside]]
        opaque = expected >= 0
        count = int(opaque.sum())
        if count == 0:
            return 0.0, 0
        drawn = _keys_at(bgr, ys[opaque], xs[opaque])
        return float((expected[opaque] == drawn).sum()) / count, count

    def _check_exact(
        self, bgr: NDArray[np.uint8], cam: tuple[int, int], rng: np.random.Generator
    ) -> _Found:
        height, width = bgr.shape[:2]
        ys = rng.integers(0, height, SHARE_SAMPLES)
        xs = rng.integers(0, width, SHARE_SAMPLES)
        share, opaque = self._exact_share(bgr, cam, ys, xs)
        best_neighbour = max(
            self._exact_share(bgr, (cam[0] + dx, cam[1] + dy), ys, xs)[0]
            for dx, dy in _NEIGHBOURS
        )
        return _Found(cam[0], cam[1], share, share / max(best_neighbour, 1e-3), opaque)

    # ---- above 1:1

    def register_scaled(
        self,
        bgr: NDArray[np.uint8],
        seed: tuple[int, int] | None,
        rng: np.random.Generator,
    ) -> tuple[_Found | None, tuple[int, int], str]:
        """The camera on a client that upscales its play area, the play
        area's size, and what was tried: around the seed, then over the
        whole map."""
        height, width = bgr.shape[:2]
        widths = play_area_widths(width, height)
        ys = rng.integers(0, int(height * (1 - UI_BAND)), NEAR_SAMPLES)
        xs = rng.integers(0, width, NEAR_SAMPLES)
        tried: list[str] = []
        searches: list[tuple[str, list[tuple[int, int]], int]] = []
        if seed is not None:
            searches.append(("scaled seeded", [seed], SEEDED_REACH))
        searches.append(("scaled global", [], COARSE))
        view = (round(width * PLAY_AREA_HEIGHT / height), PLAY_AREA_HEIGHT)
        for method, candidates, reach in searches:
            if not candidates:
                candidates = self._coarse_candidates(bgr, view)
            if not candidates:
                tried.append(f"{method}: no candidate")
                continue
            found, play_area = self._climb_scaled(
                bgr, candidates, reach, widths, ys, xs
            )
            summary = (
                f"{method}: {len(candidates)} candidates, play area "
                f"{play_area[0]}x{play_area[1]}, near share {found.share:.2f}, "
                f"sharpness {found.sharpness:.2f}, {found.opaque} opaque"
            )
            if (
                found.opaque >= MIN_OPAQUE_SAMPLES
                and found.share >= MIN_NEAR_SHARE
                and found.sharpness >= MIN_NEAR_SHARPNESS
            ):
                return found, play_area, summary
            tried.append(summary)
        return None, view, "; ".join(tried)

    def _climb_scaled(
        self,
        bgr: NDArray[np.uint8],
        candidates: list[tuple[int, int]],
        reach: int,
        widths: tuple[int, ...],
        ys: NDArray[np.int64],
        xs: NDArray[np.int64],
    ) -> tuple[_Found, tuple[int, int]]:
        """The best camera near any candidate, by near share, and the play
        area width that draws it best."""
        height, width = bgr.shape[:2]
        scores: dict[tuple[int, int, int], tuple[float, int]] = {}

        def near(cam: tuple[int, int], view_w: int) -> tuple[float, int]:
            key = (cam[0], cam[1], view_w)
            if key not in scores:
                scale = (width / view_w, height / PLAY_AREA_HEIGHT)
                scores[key] = self._near_share(bgr, cam, ys, xs, scale)
            return scores[key]

        def score(cam: tuple[int, int], view_w: int) -> float:
            share, opaque = near(cam, view_w)
            return share if opaque >= MIN_OPAQUE_SAMPLES else 0.0

        def climb(start: tuple[int, int], view_w: int) -> tuple[int, int]:
            here = start
            while True:
                step = max(
                    ((here[0] + dx, here[1] + dy) for dx, dy in ((0, 0), *_NEIGHBOURS)),
                    key=lambda c: score(c, view_w),
                )
                if step == here:
                    return here
                here = step

        first = widths[-1]
        best = max(
            (
                climb(max(_grid(cam, reach), key=lambda c: score(c, first)), first)
                for cam in candidates
            ),
            key=lambda c: score(c, first),
        )
        # The width is chosen where the camera is: one pixel of width moves
        # the far edge by less than one of the camera's.
        cams = {w: climb(best, w) for w in widths}
        view_w = max(widths, key=lambda w: score(cams[w], w))
        cam = cams[view_w]
        share, opaque = near(cam, view_w)
        best_neighbour = max(
            score((cam[0] + dx, cam[1] + dy), view_w) for dx, dy in _NEIGHBOURS
        )
        sharpness = share / max(best_neighbour, 1e-3)
        return _Found(cam[0], cam[1], share, sharpness, opaque), (
            view_w,
            PLAY_AREA_HEIGHT,
        )

    def _near_share(
        self,
        bgr: NDArray[np.uint8],
        cam: tuple[int, int],
        ys: NDArray[np.int64],
        xs: NDArray[np.int64],
        scale: tuple[float, float],
    ) -> tuple[float, int]:
        """The share of sampled client pixels within `NEAR_TOLERANCE` of the
        render upscaled bilinearly by `scale`, with the camera at `cam`; and
        how many fell wholly on the render's opaque pixels."""
        u = (xs + 0.5) / scale[0] - 0.5 + cam[0]
        v = (ys + 0.5) / scale[1] - 0.5 + cam[1]
        x0 = np.floor(u).astype(np.int64)
        y0 = np.floor(v).astype(np.int64)
        inside = (x0 >= 0) & (x0 + 1 < self.width) & (y0 >= 0) & (y0 + 1 < self.height)
        x0, y0, u, v, sx, sy = (
            x0[inside],
            y0[inside],
            u[inside],
            v[inside],
            xs[inside],
            ys[inside],
        )
        op = self.opaque
        whole = op[y0, x0] & op[y0, x0 + 1] & op[y0 + 1, x0] & op[y0 + 1, x0 + 1]
        x0, y0, u, v, sx, sy = (
            x0[whole],
            y0[whole],
            u[whole],
            v[whole],
            sx[whole],
            sy[whole],
        )
        count = len(x0)
        if count == 0:
            return 0.0, 0
        fx = (u - x0)[:, None]
        fy = (v - y0)[:, None]
        rgb = self.rgb

        def at(yy: NDArray[np.int64], xx: NDArray[np.int64]) -> NDArray[np.float64]:
            return rgb[yy, xx].astype(np.float64)

        upscaled = (
            at(y0, x0) * (1 - fx) * (1 - fy)
            + at(y0, x0 + 1) * fx * (1 - fy)
            + at(y0 + 1, x0) * (1 - fx) * fy
            + at(y0 + 1, x0 + 1) * fx * fy
        )
        diff = np.abs(upscaled[:, ::-1] - bgr[sy, sx]).max(axis=1)
        return float((diff <= NEAR_TOLERANCE).mean()), count

    def _coarse_render(self) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """The render's gray (centred on 0, 0 where transparent) and its wholly
        opaque cells, at 1/`COARSE`; made on first use."""
        if self._coarse is None:
            gray = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
            gray[~self.opaque] = 0
            factor = 1 / COARSE
            small = cv2.resize(
                gray / 255 - 0.5,
                None,
                fx=factor,
                fy=factor,
                interpolation=cv2.INTER_AREA,
            )
            cover = cv2.resize(
                self.opaque.astype(np.float32),
                None,
                fx=factor,
                fy=factor,
                interpolation=cv2.INTER_AREA,
            )
            mask = (cover >= 0.99).astype(np.float32)
            self._coarse = (small * mask, mask)
        return self._coarse

    def _coarse_candidates(
        self, bgr: NDArray[np.uint8], view: tuple[int, int]
    ) -> list[tuple[int, int]]:
        """The best `COARSE_CANDIDATES` cameras by masked correlation at
        1/`COARSE`, of the client less its `UI_BAND`, against the render's
        opaque cells."""
        image, mask = self._coarse_render()
        x0, y0, x1, y1 = self.camera_range(view)
        # Padded so that every camera in range is a place in the image.
        pad_x, pad_y = max(0, -x0) // COARSE + 1, max(0, -y0) // COARSE + 1
        rows, cols = image.shape
        tmpl_h, tmpl_w = round(view[1] / COARSE), round(view[0] / COARSE)
        big = np.zeros(
            (rows + 2 * pad_y + tmpl_h, cols + 2 * pad_x + tmpl_w), np.float32
        )
        big_mask = np.zeros_like(big)
        big[pad_y : pad_y + rows, pad_x : pad_x + cols] = image
        big_mask[pad_y : pad_y + rows, pad_x : pad_x + cols] = mask
        small = cv2.resize(bgr, (tmpl_w, tmpl_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
        tmpl = np.asarray(gray / 255 - 0.5, dtype=np.float32)
        tmpl_mask = np.ones_like(tmpl)
        tmpl_mask[int(tmpl_h * (1 - UI_BAND)) :] = 0
        ncc = _masked_ncc(big, big_mask, tmpl, tmpl_mask)
        cams_x = (np.arange(ncc.shape[1]) - pad_x) * COARSE
        cams_y = (np.arange(ncc.shape[0]) - pad_y) * COARSE
        ncc[:, (cams_x < x0 - COARSE) | (cams_x > x1 + COARSE)] = -2
        ncc[(cams_y < y0 - COARSE) | (cams_y > y1 + COARSE), :] = -2
        out: list[tuple[int, int]] = []
        for _ in range(COARSE_CANDIDATES):
            _, value, _, (lx, ly) = cv2.minMaxLoc(ncc)
            if value <= -1:
                break
            out.append((int(cams_x[lx]), int(cams_y[ly])))
            s = COARSE_SPACING
            ncc[max(0, ly - s) : ly + s + 1, max(0, lx - s) : lx + s + 1] = -2
        return out


def _grid(centre: tuple[int, int], reach: int) -> Iterator[tuple[int, int]]:
    """Cameras every `GRID_STEP` px within `reach` of `centre`."""
    steps = range(-reach, reach + 1, GRID_STEP)
    for dx in steps:
        for dy in steps:
            yield centre[0] + dx, centre[1] + dy


def _masked_ncc(
    image: NDArray[np.float32],
    mask: NDArray[np.float32],
    tmpl: NDArray[np.float32],
    tmpl_mask: NDArray[np.float32],
) -> NDArray[np.float32]:
    """Zero-mean normalised correlation of `tmpl` at every place in `image`,
    over the pixels both masks keep: six plain correlations, so OpenCV's FFT
    does the work. -1 where too little of the image is under the template."""

    def corr(a: NDArray[np.float32], b: NDArray[np.float32]) -> NDArray[np.float32]:
        return np.asarray(cv2.matchTemplate(a, b, cv2.TM_CCORR), dtype=np.float32)

    masked = mask * image
    n = corr(mask, tmpl_mask)
    s_it = corr(masked, tmpl_mask * tmpl)
    s_i = corr(masked, tmpl_mask)
    s_ii = corr(masked * image, tmpl_mask)
    s_t = corr(mask, tmpl_mask * tmpl)
    s_tt = corr(mask, tmpl_mask * tmpl * tmpl)
    safe = np.maximum(n, 1.0)
    cov = s_it - s_i * s_t / safe
    var = (s_ii - s_i * s_i / safe) * (s_tt - s_t * s_t / safe)
    out = (cov / np.sqrt(np.maximum(var, 1e-9))).astype(np.float32)
    out[n < MIN_COARSE_COVER * float(tmpl_mask.sum())] = -1
    return out
