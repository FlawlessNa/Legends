"""
The buffs: which of the asked-for buffs are shown, from their skill icons.

**Slots.** Each shown buff is an icon drawn over `UI/BuffIcon.img/IconBase/0`.
The icon covers the base's whole face, and is tinted and shaded on screen, so
the only pixels drawn exactly are the base's **outline**: its opaque pixels next
to a transparent one (frames: exact in every buff frame, shaded or not). A slot
is where that outline matches, and the ring just inside it isn't black, so a
black area doesn't read as a row of slots.

Slots are searched for in the top `_SEARCH_ROWS` icon heights of the client,
where the client draws them, packed leftwards from its top-right corner. When a
buff ends, the row closes up to the right (frames f008, f015). So:

- a place on the row's line where most of the outline is drawn, on three of
  its sides, but not all of it, is a slot something is over: `COVERED`;
- so is a row with a hole one icon wide or more;
- the rightmost slot's place is remembered, per client size; a row that starts
  further left than that is `COVERED` too.

The row's line comes from a whole slot, or from memory. A reader that has never
seen the row, looking at a frame where a cursor hides every slot's outline,
reads no buff: nothing tells that from no buff at all.

**Which buff.** Each slot is compared with each asked-for skill's icon from the
catalogue (`ReaderSprites.skill_icon`), by normalised correlation (zero-mean,
over the icon's opaque pixels inside the outline). The countdown band, where the
client draws the seconds left over the icon in the last minute, is left out. A
slot is the asked-for buff that correlates best, if it reaches
`MATCH_THRESHOLD`.

**Freshness** (`BuffState.elapsed`) isn't built: how the expiry shade is drawn
is to be taken from frames of each buff fresh, mid-way and nearly expired, which
don't exist yet (#312). Until then `elapsed` is `None`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading

from .locator import FrameCheck
from .sprites import Declaration, Profile, ReaderSprites

ICON_BASE = "UI/BuffIcon.img/IconBase/0"


def _buff_names(profile: Profile) -> tuple[str, ...]:
    return profile.buffs


BUFFS = Declaration("buffs", canvases=(ICON_BASE,), skill_icons=_buff_names)
"""The slot's base, and the icon of each buff the profile keeps up."""

MATCH_THRESHOLD = 0.43
"""A slot correlating at least this well with an asked-for icon shows that buff.
Chosen on frame set `v1` (f007-f015): the lowest correlation of a shown buff
with its own icon was 0.597 (Nimble Feet, half shaded, f014), the highest with
another skill's icon 0.265 (Haste over Nimble Feet, f014). It sits halfway, with
a margin of about 0.17 either side."""

_COUNTDOWN_ROWS = (10, 23)
"""The icon rows the countdown's digits cover, end excluded: frames show their
yellow on rows 12 to 20, and the digits' dark outline adds a row or two."""
_SEARCH_ROWS = 3
"""Slots are searched for in this many icon heights from the client's top."""
_DARK = 50.0
"""The ring inside the outline is brighter than this, on average over its
pixels and channels, in a slot: it is the base's light edge, tinted or shaded.
Frame set `v1`: the darkest slot's ring averaged 103.8 (f015, fully shaded);
where the outline matched in a black area, the ring averaged 0.2 at most."""
_PART_SHARE = 0.6
"""A place on the buff row's line where at least this share of the outline is
drawn exactly, but not all of it, on `_PART_SIDES` of its sides, with the ring
inside it light, is a slot something is over."""
_PART_SIDES = 3
"""Half of a slot hidden still leaves three sides of its outline; a window's
black corner shows two."""
_TOLERANCE = 0.5


@dataclass(frozen=True, slots=True)
class BuffState:
    """
    One buff on screen.

    :ivar shown: Its icon is drawn.
    :ivar elapsed: When shown, how much of its icon the expiry shade covers,
        from 0.0 (fresh) to 1.0 (expired). `None` until it is built (see the
        module's docstring), and always when not shown.
    """

    shown: bool
    elapsed: float | None = None


@dataclass(frozen=True, slots=True)
class _Icon:
    """An icon's comparable pixels: a mask, and their zero-mean unit vector."""

    mask: NDArray[np.bool_]
    vector: NDArray[np.float64]


class BuffsReader:
    """
    Reads the buffs from a `Frame`, remembering where its row starts.

    One per bot, built with the bot's shared `FrameCheck`. It reads the buffs
    whose icons the bot's `ReaderSprites` hold: those of the profile's `buffs`.
    """

    def __init__(self, sprites: ReaderSprites, frame_check: FrameCheck) -> None:
        self._frame_check = frame_check
        self._sprites = sprites
        base = sprites.canvas(ICON_BASE).rgba
        opaque = base[:, :, 3] == 255
        self._outline = _edge(opaque)
        self._inside = opaque & ~self._outline
        self._ring = _edge(self._inside)
        self._height, self._width = opaque.shape
        self._outline_bgr = np.ascontiguousarray(base[:, :, 2::-1])
        colours = np.unique(self._outline_bgr[self._outline], axis=0)
        if len(colours) != 1:
            raise ValueError(f"{ICON_BASE}'s outline isn't drawn in one colour")
        self._outline_colour = colours[0]
        self._outline_mask = np.repeat(self._outline[:, :, None], 3, axis=2).astype(
            np.float32
        )
        self._ring_mask = np.repeat(self._ring[:, :, None], 3, axis=2).astype(
            np.float32
        )
        rows, cols = np.indices(opaque.shape)
        quarter_h, quarter_w = self._height // 4, self._width // 4
        self._sides = tuple(
            self._outline & side
            for side in (
                rows < quarter_h,
                rows >= self._height - quarter_h,
                cols < quarter_w,
                cols >= self._width - quarter_w,
            )
        )
        self._icons: dict[str, _Icon] = {}
        # The rightmost slot's distance from the client's right edge, and its
        # top, for the client size it was seen at.
        self._first: tuple[int, int] | None = None
        self._client_size: tuple[int, int] | None = None

    def read(self, frame: Frame, buffs: Iterable[str]) -> Reading[dict[str, BuffState]]:
        """
        Whether each of `buffs` is shown in `frame`. Never raises because of
        what is on screen.

        :raises KeyError: A buff's icon wasn't loaded: it isn't in the
            profile's `buffs`.
        """
        icons = {name: self._icon(name) for name in buffs}
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        if frame.client_size != self._client_size:
            self._client_size = frame.client_size
            self._first = None
        slots, hidden = self._hidden(frame, frame.pixels)
        if hidden:
            return Reading.covered(frame.captured_at, hidden)
        shown: set[str] = set()
        for x, y in slots:
            patch = frame.pixels[y : y + self._height, x : x + self._width]
            scores = {name: _correlation(patch, icon) for name, icon in icons.items()}
            if not scores:
                break
            best = max(scores, key=scores.__getitem__)
            if scores[best] >= MATCH_THRESHOLD:
                shown.add(best)
        return Reading.read(
            {name: BuffState(name in shown) for name in icons}, frame.captured_at
        )

    def slots(self, pixels: NDArray[np.uint8]) -> list[tuple[int, int]]:
        """Every slot's top-left corner, in client pixels, right to left and
        top to bottom."""
        return self._search(pixels)[0]

    def _search(
        self, pixels: NDArray[np.uint8]
    ) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        """The slots, and where a slot is drawn only in part: most of its
        outline exact, not all of it, away from any whole slot."""
        area = np.ascontiguousarray(pixels[: self._height * _SEARCH_ROWS])
        if area.shape[0] < self._height or area.shape[1] < self._width:
            return [], []
        count = int(self._outline.sum())
        outline = (
            cv2.matchTemplate(
                area, self._outline_bgr, cv2.TM_SQDIFF, mask=self._outline_mask
            )
            / count
        )
        exact = (area == self._outline_colour).all(axis=2).astype(np.float32)
        share = (
            cv2.matchTemplate(exact, self._outline.astype(np.float32), cv2.TM_CCORR)
            / count
        )
        ring = cv2.matchTemplate(
            area.astype(np.float32),
            np.ones(self._outline_bgr.shape, np.float32),
            cv2.TM_CCORR,
            mask=self._ring_mask,
        ) / (3 * int(self._ring.sum()))
        light = ring > _DARK
        whole = _corners((outline <= _TOLERANCE) & light)
        part = [
            (x, y)
            for x, y in _corners(
                (share >= _PART_SHARE) & (outline > _TOLERANCE) & light
            )
            if all(
                abs(x - wx) > self._width // 2 or abs(y - wy) > self._height // 2
                for wx, wy in whole
            )
            and self._sides_shown(exact[y : y + self._height, x : x + self._width])
            >= _PART_SIDES
        ]
        return whole, part

    def _sides_shown(self, exact: NDArray[np.float32]) -> int:
        """How many of the outline's four sides are at least half drawn."""
        drawn = exact.astype(bool) & self._outline
        return sum(int(drawn[side].sum() * 2 >= side.sum()) for side in self._sides)

    def _hidden(
        self, frame: Frame, pixels: NDArray[np.uint8]
    ) -> tuple[list[tuple[int, int]], str]:
        """
        The slots, and why some slot isn't drawn whole, or `""`: a slot on the
        row's line drawn only in part, a hole in the row, or a row that starts
        left of where it did.
        """
        slots, part = self._search(pixels)
        if slots:
            line = slots[0][1]
        elif self._first is not None:
            line = self._first[1]
        else:
            return slots, ""
        for x, y in part:
            if y == line:
                return slots, f"a buff slot at ({x}, {y}) is drawn only in part"
        if not slots:
            return slots, ""
        row = [x for x, y in slots if y == line]
        for right, left in pairwise(row):
            if right - left != self._width:
                return (
                    slots,
                    f"a buff slot between x={left} and x={right} isn't drawn whole",
                )
        first = (frame.client_size[0] - row[0], line)
        if self._first is None or first[0] < self._first[0]:
            self._first = first
        elif first != self._first:
            return slots, "the first buff slot isn't drawn whole"
        return slots, ""

    def _icon(self, name: str) -> _Icon:
        icon = self._icons.get(name)
        if icon is None:
            rgba = self._sprites.skill_icon(name).rgba
            mask = (rgba[:, :, 3] == 255) & self._inside[
                : rgba.shape[0], : rgba.shape[1]
            ]
            mask[_COUNTDOWN_ROWS[0] : _COUNTDOWN_ROWS[1]] = False
            icon = _Icon(mask, _unit(rgba[:, :, 2::-1][mask]))
            self._icons[name] = icon
        return icon


def _corners(found: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """The `(x, y)` of each true cell, right to left and top to bottom."""
    ys, xs = np.nonzero(found)
    return sorted(
        zip(xs.tolist(), ys.tolist(), strict=True), key=lambda s: (s[1], -s[0])
    )


def _edge(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """The pixels of `mask` next to one outside it, or to the border."""
    padded = np.pad(mask, 1)
    interior = (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    return mask & ~interior


def _unit(pixels: NDArray[np.uint8]) -> NDArray[np.float64]:
    """`pixels`, flattened, less their mean, at length 1; zeros when flat."""
    values = pixels.astype(np.float64).ravel()
    values -= values.mean()
    norm = float(np.linalg.norm(values))
    return values / norm if norm else values


def _correlation(patch: NDArray[np.uint8], icon: _Icon) -> float:
    """Normalised correlation of a slot's pixels with an icon's, over its mask."""
    if patch.shape[:2] != icon.mask.shape:
        return 0.0
    return float(_unit(patch[icon.mask]) @ icon.vector)
