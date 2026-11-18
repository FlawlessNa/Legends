"""
Picking the bot's own character among several `Character` detections.

The model also fires on other players. The kept box is the one whose name tag
reads as the IGN; when no tag reads (it is hidden), the one closest to the box
kept last; otherwise the most confident.

A tag is read with the `name-tag` glyphs (`NameTagReader`,
`maple.screen.name_tag`), never OCR (#457). A picker given no reader reads no
tag and keeps the box by its fallbacks alone.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from fuzzywuzzy import fuzz

from maple.screen.font import GlyphSet
from maple.screen.name_tag import read_name_tag
from maple.screen.position import tag_upscale

# Name-tag strip, read from the image the detection ran on, in play-area px:
# multiplied by the tag scale (`tag_upscale`) on an upscaled client.
TAG_STRIP_GAP_PX = 0  # between the box's bottom edge and the strip
# Added to the box's width, centred on the box: wide enough for a long name
# (a 12-letter one is 88 px on frame set v4) under a narrow box. The reader
# reads the tag nearest the strip's middle.
TAG_STRIP_EXTRA_WIDTH_PX = 80
TAG_STRIP_HEIGHT_PX = 18

# The threshold the IGN was fuzzy-matched with when it located the client.
TAG_MATCH_RATIO = 90  # fuzz.ratio, 0..100, strictly exceeded

# Continuity between frames.
TRACK_MAX_DISTANCE_PX = 150.0  # box-centre to box-centre
TRACK_MAX_AGE_S = 5.0  # the last kept box is forgotten after this long

Box4 = tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass(frozen=True)
class Candidate:
    box: Box4
    confidence: float


class TagReader(Protocol):
    def read_tag(self, strip: np.ndarray, client_size: tuple[int, int]) -> str:
        """The name on the tag in `strip`, cut from a client of `client_size`."""
        ...

    def fold(self, text: str) -> str:
        """`text` as two readings of one name compare equal: case aside, and
        letters the font draws alike as one."""
        ...


class NameTagReader:
    """Reads the white name tag under a character with the `name-tag` glyphs
    (`maple.screen.name_tag`): a letter with no glyph reads U+FFFD."""

    def __init__(self, glyphs: GlyphSet) -> None:
        self._glyphs = glyphs
        self._alike = {
            char: group[0] for group in glyphs.alike.values() for char in group
        }

    def read_tag(self, strip: np.ndarray, client_size: tuple[int, int]) -> str:
        return read_name_tag(self._glyphs, strip, client_size)

    def fold(self, text: str) -> str:
        """Case aside, and each letter of a group the font draws alike (Arial's
        `I` and `l`, `GlyphSet.alike`) as the group's first."""
        return "".join(self._alike.get(char, char) for char in text).casefold()


def tag_strip(image: np.ndarray, box: Box4, scale: float = 1.0) -> np.ndarray | None:
    """The strip under `box`, clipped to the image; None when nothing is left.
    `scale` is the client's tag scale (`tag_upscale`)."""
    x1, _, x2, y2 = box
    centre = (x1 + x2) / 2
    half = (x2 - x1 + TAG_STRIP_EXTRA_WIDTH_PX * scale) / 2
    top = y2 + round(TAG_STRIP_GAP_PX * scale)
    left, right = (
        max(0, round(centre - half)),
        min(image.shape[1], round(centre + half)),
    )
    bottom = min(image.shape[0], top + round(TAG_STRIP_HEIGHT_PX * scale))
    if right <= left or bottom <= top:
        return None
    return image[top:bottom, left:right]


def _centre(box: Box4) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


class OwnCharacterPicker:
    def __init__(
        self,
        ign: str,
        reader: TagReader | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ign = ign
        self._reader = reader
        self._clock = clock
        self._last: Box4 | None = None
        self._last_at = 0.0

    def pick(self, image: np.ndarray, candidates: Sequence[Candidate]) -> Box4 | None:
        """The candidate that is the bot's own character; None when there is none."""
        if not candidates:
            return None
        if len(candidates) == 1:
            kept = candidates[0].box
        else:
            kept = (
                self._by_tag(image, candidates)
                or self._by_continuity(candidates)
                or max(candidates, key=lambda c: c.confidence).box
            )
        self._last, self._last_at = kept, self._clock()
        return kept

    def _by_tag(
        self, image: np.ndarray, candidates: Sequence[Candidate]
    ) -> Box4 | None:
        if self._reader is None:
            return None
        client_size = (image.shape[1], image.shape[0])
        scale = tag_upscale(client_size) or 1.0
        ign = self._reader.fold(self.ign)
        matching: list[Candidate] = []
        for cand in candidates:
            strip = tag_strip(image, cand.box, scale)
            if strip is None:
                continue
            text = self._reader.fold(self._reader.read_tag(strip, client_size))
            if fuzz.ratio(text, ign) > TAG_MATCH_RATIO:
                matching.append(cand)
        if not matching:
            return None
        return max(matching, key=lambda c: c.confidence).box

    def _by_continuity(self, candidates: Sequence[Candidate]) -> Box4 | None:
        if self._last is None:
            return None
        if self._clock() - self._last_at > TRACK_MAX_AGE_S:
            self._last = None
            return None
        lx, ly = _centre(self._last)

        def distance(cand: Candidate) -> float:
            cx, cy = _centre(cand.box)
            return float(np.hypot(cx - lx, cy - ly))

        closest = min(candidates, key=distance)
        return closest.box if distance(closest) <= TRACK_MAX_DISTANCE_PX else None
