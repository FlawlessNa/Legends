"""
Picking the bot's own character among several `Character` detections.

The model also fires on other players. The kept box is the one whose name tag
reads as the IGN; when no tag reads (it is hidden), the one closest to the box
kept last; otherwise the most confident.
"""

import string
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np
from fuzzywuzzy import fuzz

from botting.visuals import InGameBaseVisuals

# Name-tag strip, read from the image the detection ran on.
TAG_STRIP_GAP_PX = 0  # between the box's bottom edge and the strip
TAG_STRIP_EXTRA_WIDTH_PX = 40  # added to the box's width, centred on the box
TAG_STRIP_HEIGHT_PX = 18

# The threshold the IGN was fuzzy-matched with when it located the client.
TAG_MATCH_RATIO = 90  # fuzz.ratio, 0..100, strictly exceeded

# Continuity between frames.
TRACK_MAX_DISTANCE_PX = 150.0  # box-centre to box-centre
TRACK_MAX_AGE_S = 5.0  # the last kept box is forgotten after this long

TAG_TEXT_MIN_GRAY = 200  # 0..255, white tag text
TAG_UPSCALE = 3

Box4 = tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass(frozen=True)
class Candidate:
    box: Box4
    confidence: float


class TagReader(Protocol):
    def read_tag(self, strip: np.ndarray) -> str: ...


class NameTagReader(InGameBaseVisuals):
    """Reads the white name tag under a character."""

    CONFIG = f"--psm 7 -c tessedit_char_whitelist={string.ascii_letters}{string.digits}"

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        text = cv2.inRange(gray, np.array([TAG_TEXT_MIN_GRAY]), np.array([255]))
        text = cv2.resize(text, None, fx=TAG_UPSCALE, fy=TAG_UPSCALE)
        return cv2.bitwise_not(text)  # dark text on white, as tesseract prefers

    def read_tag(self, strip: np.ndarray) -> str:
        return self.read_from_img(strip, self.CONFIG, confidence_level=0)


def tag_strip(image: np.ndarray, box: Box4) -> np.ndarray | None:
    """The strip under `box`, clipped to the image; None when nothing is left."""
    x1, _, x2, y2 = box
    centre = (x1 + x2) / 2
    half = (x2 - x1 + TAG_STRIP_EXTRA_WIDTH_PX) / 2
    top = y2 + TAG_STRIP_GAP_PX
    left, right = (
        max(0, round(centre - half)),
        min(image.shape[1], round(centre + half)),
    )
    bottom = min(image.shape[0], top + TAG_STRIP_HEIGHT_PX)
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
        self._reader = reader or NameTagReader()
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
        matching: list[Candidate] = []
        for cand in candidates:
            strip = tag_strip(image, cand.box)
            if strip is None:
                continue
            text = self._reader.read_tag(strip)
            if fuzz.ratio(text.lower(), self.ign.lower()) > TAG_MATCH_RATIO:
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
