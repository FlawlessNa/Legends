"""Exact sprite matching over opaque pixels.

Only pixels with alpha 255 count: alpha 251-254 is blended with the background
on screen, so it cannot be compared exactly.

The haystack is BGR (as captured); the sprite is RGBA.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import cv2
import numpy as np

_OPAQUE = 255
# matchTemplate works in float32 and can drift from the exact sum; candidates are
# gathered with this much slack, then re-scored exactly.
_SLACK = 1.0


@dataclass(frozen=True)
class Hit:
    x: int
    y: int
    error: float


def _prepare(sprite_rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    if sprite_rgba.ndim != 3 or sprite_rgba.shape[2] != 4:
        raise ValueError("sprite_rgba must be an H x W x 4 array")
    mask = sprite_rgba[:, :, 3] == _OPAQUE
    count = int(mask.sum())
    if count == 0:
        raise ValueError("sprite has no pixel with alpha 255")
    bgr = np.ascontiguousarray(sprite_rgba[:, :, 2::-1])
    return bgr, mask, count


def match(
    haystack: np.ndarray,
    sprite_rgba: np.ndarray,
    region: tuple[int, int, int, int] | None = None,
    tolerance: float = 0.5,
) -> list[Hit]:
    """Every position whose mean squared opaque-pixel error is within ``tolerance``.

    ``region`` is ``(x, y, width, height)`` in haystack coordinates; hits are
    reported in haystack coordinates. ``0.0`` is an exact match.
    """
    bgr, mask, count = _prepare(sprite_rgba)
    ox = oy = 0
    area = haystack
    if region is not None:
        x, y, w, h = region
        x0, y0 = max(x, 0), max(y, 0)
        x1 = min(x + w, haystack.shape[1])
        y1 = min(y + h, haystack.shape[0])
        if x1 <= x0 or y1 <= y0:
            return []
        area = haystack[y0:y1, x0:x1]
        ox, oy = x0, y0
    sh, sw = mask.shape
    if area.shape[0] < sh or area.shape[1] < sw:
        return []

    mask3 = np.repeat(mask[:, :, None], 3, axis=2).astype(np.float32)
    scores = cv2.matchTemplate(
        np.ascontiguousarray(area), bgr, cv2.TM_SQDIFF, mask=mask3
    )
    ys, xs = np.nonzero(scores / count <= tolerance + _SLACK)

    sprite_px = bgr[mask].astype(np.int64)
    hits: list[Hit] = []
    for cy, cx in zip(ys.tolist(), xs.tolist(), strict=True):
        patch = area[cy : cy + sh, cx : cx + sw][mask].astype(np.int64)
        error = float(((patch - sprite_px) ** 2).sum()) / count
        if error <= tolerance:
            hits.append(Hit(cx + ox, cy + oy, error))
    return hits


def match_best(
    haystack: np.ndarray,
    sprite_rgba: np.ndarray,
    region: tuple[int, int, int, int] | None = None,
    tolerance: float = 0.5,
) -> Hit | None:
    """The lowest-error hit, or ``None``."""
    hits = match(haystack, sprite_rgba, region, tolerance)
    return min(hits, key=lambda h: h.error) if hits else None


def read_glyphs(
    strip: np.ndarray,
    glyphs: Mapping[str, np.ndarray],
    tolerance: float = 0.5,
) -> str:
    """Read a string drawn with ``glyphs`` (name -> RGBA sprite).

    Hits are accepted by opaque area, largest first, skipping any whose box
    overlaps one already accepted; names come back ordered by ``x``.
    """
    candidates: list[tuple[int, int, str, int, int, int, int]] = []
    for name, sprite in glyphs.items():
        _, mask, count = _prepare(sprite)
        h, w = mask.shape
        for hit in match(strip, sprite, tolerance=tolerance):
            candidates.append((count, hit.x, name, hit.x, hit.y, w, h))
    candidates.sort(key=lambda c: (-c[0], c[1]))

    accepted: list[tuple[str, int, int, int, int]] = []
    for _, _, name, x, y, w, h in candidates:
        if any(
            x < ax + aw and ax < x + w and y < ay + ah and ay < y + h
            for _, ax, ay, aw, ah in accepted
        ):
            continue
        accepted.append((name, x, y, w, h))
    accepted.sort(key=lambda a: a[1])
    return "".join(a[0] for a in accepted)
