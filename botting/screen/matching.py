"""Exact sprite matching over opaque pixels.

Only pixels with alpha 255 count: alpha 251-254 is blended with the background
on screen, so it cannot be compared exactly.

The haystack is BGR (as captured); the sprite is RGBA.
"""

from __future__ import annotations

import weakref
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


@dataclass(frozen=True)
class _Prepared:
    bgr: np.ndarray
    mask: np.ndarray
    count: int
    mask3: np.ndarray
    sprite_px: np.ndarray


# A sprite is matched many times per second and never changes, so what is derived
# from it is kept, for as long as the array lives.
_PREPARED: dict[int, tuple[weakref.ref[np.ndarray], _Prepared]] = {}


def _prepared(sprite_rgba: np.ndarray) -> _Prepared:
    key = id(sprite_rgba)
    cached = _PREPARED.get(key)
    if cached is not None and cached[0]() is sprite_rgba:
        return cached[1]
    bgr, mask, count = _prepare(sprite_rgba)
    prepared = _Prepared(
        bgr,
        mask,
        count,
        np.repeat(mask[:, :, None], 3, axis=2).astype(np.float32),
        bgr[mask].astype(np.int64),
    )
    _PREPARED[key] = (
        weakref.ref(sprite_rgba, lambda _, key=key: _PREPARED.pop(key, None)),
        prepared,
    )
    return prepared


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
    prepared = _prepared(sprite_rgba)
    bgr, mask, count = prepared.bgr, prepared.mask, prepared.count
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

    scores = cv2.matchTemplate(
        np.ascontiguousarray(area), bgr, cv2.TM_SQDIFF, mask=prepared.mask3
    )
    ys, xs = np.nonzero(scores / count <= tolerance + _SLACK)

    sprite_px = prepared.sprite_px
    hits: list[Hit] = []
    for cy, cx in zip(ys.tolist(), xs.tolist(), strict=True):
        patch = area[cy : cy + sh, cx : cx + sw][mask].astype(np.int64)
        error = float(((patch - sprite_px) ** 2).sum()) / count
        if error <= tolerance:
            hits.append(Hit(cx + ox, cy + oy, error))
    return hits


def matches_at(
    haystack: np.ndarray,
    sprite_rgba: np.ndarray,
    x: int,
    y: int,
    tolerance: float = 0.5,
) -> bool:
    """Whether the sprite is drawn with its top-left at ``(x, y)``: the `match` score
    at that one position, without searching. False when it falls outside."""
    prepared = _prepared(sprite_rgba)
    h, w = prepared.mask.shape
    if x < 0 or y < 0 or y + h > haystack.shape[0] or x + w > haystack.shape[1]:
        return False
    patch = haystack[y : y + h, x : x + w][prepared.mask].astype(np.int64)
    error = float(((patch - prepared.sprite_px) ** 2).sum()) / prepared.count
    return error <= tolerance


def match_best(
    haystack: np.ndarray,
    sprite_rgba: np.ndarray,
    region: tuple[int, int, int, int] | None = None,
    tolerance: float = 0.5,
) -> Hit | None:
    """The lowest-error hit, or ``None``."""
    hits = match(haystack, sprite_rgba, region, tolerance)
    return min(hits, key=lambda h: h.error) if hits else None


@dataclass(frozen=True)
class GlyphHit:
    """A glyph accepted in a strip: its name and the box it occupies."""

    name: str
    x: int
    y: int
    width: int
    height: int


def find_glyphs(
    strip: np.ndarray,
    glyphs: Mapping[str, np.ndarray],
    tolerance: float = 0.5,
) -> list[GlyphHit]:
    """Where ``glyphs`` (name -> RGBA sprite) are drawn in ``strip``, left to right.

    Hits are accepted by opaque area, largest first, skipping any whose box
    overlaps one already accepted.
    """
    candidates: list[tuple[int, int, str, int, int, int, int]] = []
    for name, sprite in glyphs.items():
        prepared = _prepared(sprite)
        count = prepared.count
        h, w = prepared.mask.shape
        for hit in match(strip, sprite, tolerance=tolerance):
            candidates.append((count, hit.x, name, hit.x, hit.y, w, h))
    candidates.sort(key=lambda c: (-c[0], c[1]))

    accepted: list[GlyphHit] = []
    for _, _, name, x, y, w, h in candidates:
        if any(
            x < a.x + a.width and a.x < x + w and y < a.y + a.height and a.y < y + h
            for a in accepted
        ):
            continue
        accepted.append(GlyphHit(name, x, y, w, h))
    accepted.sort(key=lambda a: a.x)
    return accepted


def read_glyphs(
    strip: np.ndarray,
    glyphs: Mapping[str, np.ndarray],
    tolerance: float = 0.5,
) -> str:
    """Read a string drawn with ``glyphs`` (name -> RGBA sprite).

    A glyph that isn't found (covered, say) is missing from the string without
    a trace: use `find_glyphs` to see where the glyphs are.
    """
    return "".join(hit.name for hit in find_glyphs(strip, glyphs, tolerance))
