"""
The characters on screen, by their feet (#391, epic #302 Part 2, item 4 and
decision N3): a `CharacterFinder` interface, with two implementations.

- `NameTagFinder` finds name tags, white text on a dark translucent box drawn
  just under a character's feet, ported from the POCs
  (`toolkit/poc_tracking/hybrid_tracker.py`). It lists every tag it finds, and
  tells ours apart once it has learned it (`learn_own`): our tag's width and
  appearance, from 3 sightings where the minimap puts our character. No text is
  read. Where the map's art drawn in front of our character hides part of our
  tag, it finds ours on what is seen, when asked where to look and what is
  hidden (`find_own_hidden`, #517).
- `YoloCharacterFinder` wraps a YOLO detection model's `Character` boxes. Its
  weights are trained elsewhere, and nothing here waits on them.

Feet are in **client px**, as captured: scaling them to the play area's render
size and adding the camera is `PositionFusion`'s job (#392).

No value here is read from the client. The tag's thresholds come from the POCs;
`TAG_TO_FEET` and the match scores were measured on frame set v3
(`tests/frames/README.md`), and the sizes the play area is upscaled at are
`camera.PLAY_AREAS`, measured there too. `HIDDEN_PART` was read off a
Session's screen recording, not a labelled frame set.
"""

from __future__ import annotations

import collections
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading

from .camera import play_area_size

Box = tuple[int, int, int, int]
"""`(x0, y0, x1, y1)` in client px, the right and bottom edges exclusive."""

type Covered = Callable[[Box], NDArray[np.bool_]]
"""For a box of the client, `(x0, y0, x1, y1)`, True on each pixel the map's
art drawn in front of our character covers (`maple.model.world.FrontArt`)."""

# --------------------------------------------------------------------- the interface


@dataclass(frozen=True, slots=True)
class CharacterSighting:
    """
    One character seen on screen.

    :ivar feet: The feet, `(x, y)` in client px.
    :ivar source: What saw it: `"name tag"` or `"yolo"`.
    :ivar confidence: The source's own score, 0 to 1: the share of dark pixels
        around a tag's text, the match score of our learned tag, or YOLO's
        confidence. Scores of different sources don't compare.
    :ivar own: True for the one sighting the finder knows is our character
        (`NameTagFinder`, once it has learned our tag). False says only that
        the finder can't tell, not that it is someone else.
    :ivar box: What the feet were taken from: the tag's text, or YOLO's box. A
        tag cut by the client's edge has the box it would have uncut.
    """

    feet: tuple[float, float]
    source: str
    confidence: float
    own: bool = False
    box: Box | None = None


class CharacterFinder(Protocol):
    """Finds the characters on screen (`PositionFusion` picks ours)."""

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        """
        Every character seen on `frame`. `READ` with an empty list when it
        looked and saw none; `UNSURE` when the frame can't be trusted or the
        finder can't look at a frame of its size.
        """
        ...

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        """
        Tell the finder that our character's feet are about at `near` (client
        px) on `frame`, as the minimap puts them. True once the finder can tell
        our character apart on frames of this size; a finder that can't learn
        always answers False.
        """
        ...

    def find_own_hidden(
        self, frame: Frame, near: tuple[float, float], covered: Covered
    ) -> CharacterSighting | None:
        """
        Our character about at `near` (client px), where `find` didn't find
        it because something drawn in front of it hides part of it: matched
        on what `covered` doesn't say is hidden. `None` when it isn't found
        so, or the finder can't tell ours apart.
        """
        ...


# ----------------------------------------------------------------------- tag scale


def tag_upscale(client_size: tuple[int, int]) -> float | None:
    """
    How many client px a name tag's 1:1 pixel covers at this client size, or
    None for a size not measured (`play_area_size`): 1 up to 1366x768, where
    the play area is drawn 1:1; `height / 768` where it is drawn 768 high and
    upscaled.
    """
    play_area = play_area_size(client_size)
    if play_area is None:
        return None
    return client_size[1] / play_area[1]


# ------------------------------------------------------------------------ name tags

TAG_TO_FEET = 5.0
"""The feet are this many play-area px above the top of the tag's white text:
the POC's value (`hybrid_tracker`), kept after fitting it on frame set v3's
labelled feet where our learned tag is found (276 frames). The fit is 5.00 at
1:1 (120 frames, no residual), 5.26 at 1920x1080 (134, spread 0.22), 5.68 at
1920x1200 and 5.47 at 2560x1440 (11 each): an upscaled client blurs the text's
top row, and the feet then read up to 0.73 px low."""

TAG_X_TO_FEET = 0.5
"""The feet are this many play-area px right of the tag's centre column: on
rope and wall frames the centre reads 0.2 to 0.6 px left of the character's x
(`tests/frames/README.md`, "feet")."""

STATUS_BAR_ROWS = 80
"""Client px at the bottom never searched: the status bar, which shows our
character's name in white (`toolkit/poc_tracking/label_frames.py`)."""

OWN_NEAR = (16.0, 32.0)
"""How far, in play-area px, a tag's feet may be from where the minimap puts
ours for the tag to count as a sighting of ours, in x and in y: the minimap's
position is good to about one canvas px (16 virtual px), and lies up to 15 px
above the feet (`maple.screen.minimap.virtual_feet`)."""

OWN_SIGHTINGS = 3
"""Sightings of one tag width where the minimap puts our character, and of no
other tag there, before that tag is learned as ours (`hybrid_tracker`)."""

OWN_SCORE_OK = 0.75
"""The normalised correlation our learned tag needs where it is found. Measured
on frame set v3: our tag scores 0.65 and up where something hides part of it,
0.8 and up elsewhere; anything else 0.72 at most (a settings window's
"Language", a pet's tag)."""

OWN_MARGIN = 0.1
"""Our tag's best match must beat the next best, elsewhere, by this much, or
neither is taken as ours."""

EDGE_PART = 0.55
"""A tag cut by the client's left or right edge is matched by this share of
the learned tag, the end still on screen (`tests/frames/README.md`)."""

EDGE_SCORE_OK = 0.7
"""The score that end needs. Measured on frame set v3: 0.74 to 0.93 where our
tag is cut, 0.53 at most anywhere else."""

HIDDEN_PART = 0.2
"""Where the map's art drawn in front of our character hides part of our tag
(#517), the share of the tag's text pixels that must still be seen for the
rest to be matched. The rest must score `OWN_SCORE_OK` and beat any other
place by `OWN_MARGIN`, as the whole tag must, and is only looked for within
`OWN_NEAR` of where the minimap puts our character.

Read off one Session's screen recording at 1920x1080 (MPEG-4, so lossy), not
a labelled frame set, which has no hidden tag: at the top of Ellinia the
ladder's top hides our tag on 437 reads, and leaves 16 to 48 % of its text
seen (5th to 90th percentile, median 29 %). There the rest scores 0.83 and up
on 90 % of reads, at the feet's height on the foothold, and beats any other
place by 0.43 and up on 95 %. At 0.2, 349 of the 437 are found (412 at 0.15,
275 at 0.25, 9 at `EDGE_PART`). To be confirmed on the live client."""


def _white(scale: float) -> int:
    """The tag text's lightest channel is at least this (the POC's values; an
    upscaled client blurs the text)."""
    return 245 if scale == 1.0 else 190


def _dark(scale: float) -> int:
    """The tag box's brightest channel is at most this (the POC's values)."""
    return 90 if scale == 1.0 else 110


@dataclass(frozen=True, slots=True)
class _Tag:
    """A name tag's white text, and the share of dark pixels around it."""

    box: Box
    dark: float

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]


def _find_name_tags(pixels: NDArray[np.uint8], scale: float) -> list[_Tag]:
    """
    Name tags in `pixels`: white text on a dark box, letters joined across
    small gaps (`hybrid_tracker.find_name_tags`). Two tags drawn side by side
    can join into one.
    """
    lightest = _channel_min(pixels)
    white = (lightest >= _white(scale)).astype(np.uint8)
    dark = _channel_max(pixels) <= _dark(scale)
    joined = cv2.dilate(white, np.ones((1, max(3, round(7 * scale))), np.uint8))
    _, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    rows, cols = pixels.shape[:2]
    tags: list[_Tag] = []
    for x, y, w, h, _ in stats[1:].tolist():
        if not (6 * scale <= h <= 16 * scale and 12 * scale <= w <= 220 * scale):
            continue
        y0, y1 = max(0, y - 2), min(rows, y + h + 2)
        x0, x1 = max(0, x - 2), min(cols, x + w + 2)
        text = white[y0:y1, x0:x1].astype(bool)
        # Upscaling smears the text's edges into mid greys: not the box either.
        box = ~text & (lightest[y0:y1, x0:x1] < (245 if scale == 1.0 else 120))
        if box.sum() == 0 or text.sum() < 6 * scale:
            continue
        share = float(dark[y0:y1, x0:x1][box].mean())
        if share < 0.75:
            continue
        tags.append(_Tag((x, y, x + w, y + h), share))
    return tags


class NameTagFinder:
    """
    Characters by their name tags. Lists every tag it finds. Marks ours `own`
    once `learn_own` has seen one tag width `OWN_SIGHTINGS` times where the
    minimap puts our character: from then on it finds our tag by its
    appearance, even beside another tag, or cut by the client's left or right
    edge.

    What it learns is kept per tag scale (`tag_upscale`): clients that draw the
    play area 1:1 share it. At a scale not learned yet, the tag learned at the
    nearest scale is resized to it, until `learn_own` learns that scale too.
    """

    def __init__(self) -> None:
        self._learned: dict[float, NDArray[np.float32]] = {}
        self._resized: dict[float, NDArray[np.float32]] = {}
        self._widths: dict[float, collections.Counter[int]] = {}

    def learned(self, client_size: tuple[int, int]) -> bool:
        """Whether our tag can be told apart on a frame of this size."""
        scale = tag_upscale(client_size)
        return scale is not None and self._template(scale) is not None

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        at = frame.captured_at
        if not frame.ok:
            return Reading.unsure(at, f"frame not trusted: {frame.reason}")
        scale = tag_upscale(frame.client_size)
        if scale is None:
            return Reading.unsure(at, f"no tag scale measured for {frame.client_size}")
        pixels = _searched(frame.pixels)
        template = self._template(scale)
        own = None if template is None else _own(pixels, template, scale)
        sightings = [] if own is None else [own]
        for tag in _find_name_tags(pixels, scale):
            if own is not None and own.box is not None and _overlap(tag.box, own.box):
                continue  # ours again, alone or joined to a neighbour's tag
            sightings.append(
                CharacterSighting(
                    _feet(tag.box, scale), "name tag", tag.dark, box=tag.box
                )
            )
        if template is None:
            detail = "our tag not learned"
        elif own is None:
            detail = "our tag not found"
        else:
            detail = ""
        return Reading.read(sightings, at, detail)

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        scale = tag_upscale(frame.client_size)
        if scale is None or not frame.ok:
            return False
        if scale in self._learned:
            return True
        pixels = _searched(frame.pixels)
        reach_x, reach_y = OWN_NEAR[0] * scale, OWN_NEAR[1] * scale
        near_tags = [
            tag
            for tag in _find_name_tags(pixels, scale)
            if abs((feet := _feet(tag.box, scale))[0] - near[0]) <= reach_x
            and abs(feet[1] - near[1]) <= reach_y
        ]
        if len(near_tags) != 1:
            # None, or several: no telling which is ours. A tag learned at
            # another scale still tells ours apart here, resized.
            return self.learned(frame.client_size)
        tag = near_tags[0]
        widths = self._widths.setdefault(scale, collections.Counter())
        widths[tag.width] += 1
        if widths[tag.width] < OWN_SIGHTINGS:
            return self.learned(frame.client_size)
        x0, y0, x1, y1 = tag.box
        self._learned[scale] = _lightest(pixels[y0:y1, x0:x1])
        self._resized.clear()
        return True

    def find_own_hidden(
        self, frame: Frame, near: tuple[float, float], covered: Covered
    ) -> CharacterSighting | None:
        """
        Our tag, where the map's art drawn in front of our character hides
        part of it: our learned tag matched on the pixels `covered` leaves
        seen, by a normalised correlation over those pixels only, at the
        places that put the feet within `OWN_NEAR` of `near`. Found when
        `HIDDEN_PART` of its text is seen there, and it scores `OWN_SCORE_OK`
        and beats any other of those places by `OWN_MARGIN`.
        """
        scale = tag_upscale(frame.client_size)
        if scale is None or not frame.ok:
            return None
        template = self._template(scale)
        if template is None:
            return None
        pixels = _searched(frame.pixels)
        th, tw = template.shape
        rows, cols = pixels.shape[:2]
        # The tag's top left for feet at `near`: `_feet`, inverted.
        x = near[0] - (tw - 1) / 2 - TAG_X_TO_FEET * scale
        y = near[1] + TAG_TO_FEET * scale
        reach_x, reach_y = OWN_NEAR[0] * scale, OWN_NEAR[1] * scale
        x0, y0 = max(0, math.ceil(x - reach_x)), max(0, math.ceil(y - reach_y))
        x1 = min(cols, math.floor(x + reach_x) + tw)
        y1 = min(rows, math.floor(y + reach_y) + th)
        if x1 - x0 < tw or y1 - y0 < th:
            return None
        hay = _lightest(pixels[y0:y1, x0:x1])
        seen = ~covered((x0, y0, x1, y1))
        found = _match_seen(hay, seen, template, _white(scale))
        if found is None:
            return None
        score, bx, by = found
        box = (x0 + bx, y0 + by, x0 + bx + tw, y0 + by + th)
        return CharacterSighting(_feet(box, scale), "name tag", score, True, box)

    def _template(self, scale: float) -> NDArray[np.float32] | None:
        """Our tag at this scale: learned at it, else resized from the nearest
        scale learned; None before any is."""
        if scale in self._learned:
            return self._learned[scale]
        if not self._learned:
            return None
        if scale not in self._resized:
            source = min(self._learned, key=lambda s: abs(s - scale))
            factor = scale / source
            self._resized[scale] = np.asarray(
                cv2.resize(
                    self._learned[source],
                    None,
                    fx=factor,
                    fy=factor,
                    interpolation=cv2.INTER_LINEAR if factor > 1 else cv2.INTER_AREA,
                ),
                dtype=np.float32,
            )
        return self._resized[scale]


def _searched(pixels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    return pixels[: max(0, pixels.shape[0] - STATUS_BAR_ROWS)]


def _channel_min(pixels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Each pixel's darkest channel: `pixels.min(axis=2)`, which takes 38 ms on
    a 1920x1080 frame where this takes 3 (numpy reduces a 3-wide last axis
    slowly; #508)."""
    return np.minimum(np.minimum(pixels[..., 0], pixels[..., 1]), pixels[..., 2])


def _channel_max(pixels: NDArray[np.uint8]) -> NDArray[np.uint8]:
    """Each pixel's brightest channel: `pixels.max(axis=2)`, as `_channel_min`."""
    return np.maximum(np.maximum(pixels[..., 0], pixels[..., 1]), pixels[..., 2])


def _lightest(pixels: NDArray[np.uint8]) -> NDArray[np.float32]:
    return _channel_min(pixels).astype(np.float32)


def _feet(box: Box, scale: float) -> tuple[float, float]:
    """The feet over a tag's text box: `TAG_X_TO_FEET` right of its centre
    column, `TAG_TO_FEET` above its top."""
    x0, y0, x1, _ = box
    return (x0 + x1 - 1) / 2 + TAG_X_TO_FEET * scale, y0 - TAG_TO_FEET * scale


def _overlap(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _own(
    pixels: NDArray[np.uint8], template: NDArray[np.float32], scale: float
) -> CharacterSighting | None:
    found = _match_own(_lightest(pixels), template)
    if found is None:
        return None
    score, x, y = found
    th, tw = template.shape
    box = (x, y, x + tw, y + th)
    return CharacterSighting(_feet(box, scale), "name tag", score, True, box)


def _match_own(
    hay: NDArray[np.float32], text: NDArray[np.float32]
) -> tuple[float, int, int] | None:
    """
    Our tag's match `(score, x, y)` in `hay`: the whole tag's, when it scores
    `OWN_SCORE_OK` and beats any other place by `OWN_MARGIN`; else the end of
    it still on screen, where the client's left or right edge cuts it. None
    when neither is found.
    """
    th, tw = text.shape
    rows, cols = hay.shape
    if rows < th or cols < tw:
        return None
    score = _scores(hay, text)
    _, best, _, (x, y) = cv2.minMaxLoc(score)
    if best >= OWN_SCORE_OK:
        score[max(0, y - th) : y + th, max(0, x - tw) : x + tw] = -1.0
        if best - float(score.max()) >= OWN_MARGIN:
            return float(best), int(x), int(y)
        return None  # two places look like ours
    part = math.ceil(tw * EDGE_PART)
    # Its left end at the client's right edge, the rest past it.
    s, lx, ly = _best(hay[:, cols - tw :], text[:, :part])
    if s >= EDGE_SCORE_OK and lx > 0:
        return s, cols - tw + lx, ly
    # Its right end at the left edge.
    s, rx, ry = _best(hay[:, :tw], text[:, tw - part :])
    if s >= EDGE_SCORE_OK and rx < tw - part:
        return s, rx - (tw - part), ry
    return None


def _scores(
    hay: NDArray[np.float32], needle: NDArray[np.float32]
) -> NDArray[np.float32]:
    score = cv2.matchTemplate(hay, needle, cv2.TM_CCOEFF_NORMED)
    # OpenCV's normalised scores are finite or NaN (a flat window); only NaN
    # needs a value. `np.nan_to_num` also scanned the frame for infinities, 7 ms
    # on a 1920x1080 frame (#508).
    score = np.asarray(score, dtype=np.float32)
    score[np.isnan(score)] = -1.0
    return score


def _best(
    hay: NDArray[np.float32], needle: NDArray[np.float32]
) -> tuple[float, int, int]:
    _, best, _, (x, y) = cv2.minMaxLoc(_scores(hay, needle))
    return float(best), int(x), int(y)


def _match_seen(
    hay: NDArray[np.float32],
    seen: NDArray[np.bool_],
    text: NDArray[np.float32],
    white: int,
) -> tuple[float, int, int] | None:
    """
    Our tag's match `(score, x, y)` in `hay` on the pixels `seen` marks: at
    each place, `TM_CCOEFF_NORMED`'s score over the seen pixels only (the
    same score where every pixel is seen). A place counts when `HIDDEN_PART`
    of the tag's text pixels (`white` and up) are seen there; the best must
    score `OWN_SCORE_OK` and beat every other place by `OWN_MARGIN`. None
    otherwise.
    """
    th, tw = text.shape
    w = seen.astype(np.float64)
    h = hay.astype(np.float64)
    t = text.astype(np.float64)
    letters = (t >= white).astype(np.float64)
    if letters.sum() == 0:
        return None
    ones = np.ones_like(t)
    n = _correlate(w, ones)
    sh, shh = _correlate(w * h, ones), _correlate(w * h * h, ones)
    st, stt, sht = _correlate(w, t), _correlate(w, t * t), _correlate(w * h, t)
    shown = _correlate(w, letters) / letters.sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        covariance = sht - sh * st / n
        spread = (shh - sh * sh / n) * (stt - st * st / n)
        score = covariance / np.sqrt(spread)
    score[~np.isfinite(score) | (spread <= 0) | (shown < HIDDEN_PART)] = -1.0
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    best = float(score[y, x])
    if best < OWN_SCORE_OK:
        return None
    score[max(0, y - th) : y + th, max(0, x - tw) : x + tw] = -1.0
    if best - float(score.max()) < OWN_MARGIN:
        return None
    return best, int(x), int(y)


def _correlate(
    image: NDArray[np.float64], kernel: NDArray[np.float64]
) -> NDArray[np.float64]:
    """`sum(kernel * image[y:y + kh, x:x + kw])` at every place where the
    kernel lies inside `image`, in float64: sums of squared pixels outgrow
    float32's precision."""
    kh, kw = kernel.shape
    out = cv2.filter2D(image, cv2.CV_64F, kernel, anchor=(0, 0))
    return np.asarray(
        out[: image.shape[0] - kh + 1, : image.shape[1] - kw + 1], np.float64
    )


# ----------------------------------------------------------------------------- YOLO

CHARACTER_CLASS = "Character"
"""The detection model's class for a character."""

YOLO_THRESHOLD = 0.65
"""The confidence a box needs (`InGameDetectionVisuals.DEFAULT_THRESHOLD`)."""

YOLO_IOU = 0.3
"""The overlap above which YOLO merges boxes (`run_detection_model`'s)."""


class DetectionResult(Protocol):
    """The part of an `ultralytics` `Results` this reads."""

    def summary(self) -> Sequence[Mapping[str, Any]]: ...


class DetectionModel(Protocol):
    """The part of an `ultralytics.YOLO` model this calls."""

    def __call__(
        self, source: NDArray[np.uint8], *, conf: float, verbose: bool, iou: float
    ) -> Iterable[DetectionResult]: ...


class YoloCharacterFinder:
    """
    Characters by a YOLO model's `Character` boxes, the model called as
    `InGameDetectionVisuals.run_detection_model` calls it. The feet are a box's
    bottom centre. It can't tell ours apart: every sighting has `own` False.
    """

    def __init__(
        self, model: DetectionModel, threshold: float = YOLO_THRESHOLD
    ) -> None:
        self._model = model
        self._threshold = threshold

    @classmethod
    def from_weights(
        cls, weights: Path, threshold: float = YOLO_THRESHOLD
    ) -> YoloCharacterFinder:
        """A finder on the model at `weights` (a `.../weights/best.pt`)."""
        from ultralytics import YOLO  # heavy: only when weights are used

        model: Any = YOLO(str(weights), task="detect")
        return cls(model, threshold)

    def find(self, frame: Frame) -> Reading[list[CharacterSighting]]:
        at = frame.captured_at
        if not frame.ok:
            return Reading.unsure(at, f"frame not trusted: {frame.reason}")
        results = list(
            self._model(frame.pixels, conf=self._threshold, verbose=False, iou=YOLO_IOU)
        )
        if len(results) != 1:
            return Reading.unsure(at, f"{len(results)} detection results for one frame")
        sightings: list[CharacterSighting] = []
        for found in results[0].summary():
            if found["name"] != CHARACTER_CLASS:
                continue
            box = found["box"]
            x0, y0, x1, y1 = (float(box[k]) for k in ("x1", "y1", "x2", "y2"))
            sightings.append(
                CharacterSighting(
                    ((x0 + x1) / 2, y1),
                    "yolo",
                    float(found["confidence"]),
                    box=(round(x0), round(y0), round(x1), round(y1)),
                )
            )
        return Reading.read(sightings, at)

    def learn_own(self, frame: Frame, near: tuple[float, float]) -> bool:
        return False

    def find_own_hidden(
        self, frame: Frame, near: tuple[float, float], covered: Covered
    ) -> CharacterSighting | None:
        return None
