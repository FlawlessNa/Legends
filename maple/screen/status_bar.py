"""
The status bar: level, HP, MP and EXP, read exactly from its own digit sprites.

The bar is located by `UI/StatusBar.img/canvas:gaugeLabel`, with
`canvas:backgrnd1` as its fixed part, so a covered label still locates it. The
bar's origin (`Located.point`) is where the client draws the bar from; each
number sits at a `vector:` node from it. Nothing here is a measured coordinate:
every position is a vector, a sprite's origin, or a sprite's size.

Digits are read with `lvNumber/*` (the level) and `gauge/number/*` (HP, MP and
EXP). A string that doesn't parse as exactly what the bar draws is `UNSURE`,
with the string as `detail`, never a guessed number.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, GlyphHit, Reading, find_glyphs
from game_data.sprites import Sprite
from maple.screen.locator import FrameCheck, Located, Locator, Part, unreadable
from maple.screen.sprites import GAUGE_LABEL, Declaration, ReaderSprites

_BASE = "UI/StatusBar.img"
BACKGROUND = f"{_BASE}/canvas:backgrnd1"
_LEVEL_AT = f"{_BASE}/vector:posNumberLv"
_HP_AT = f"{_BASE}/gauge/vector:posNumberHp"
_MP_AT = f"{_BASE}/gauge/vector:posNumberMp"
_EXP_AT = f"{_BASE}/gauge/vector:posNumberExp"

# Glyph name in the client's tree -> the character it draws. `lvNumber/blank`
# draws nothing readable, so it isn't a glyph.
_LEVEL_DIGITS = {str(n): f"{_BASE}/lvNumber/{n}" for n in range(10)}
_GAUGE_GLYPHS = {
    **{str(n): f"{_BASE}/gauge/number/{n}" for n in range(10)},
    "[": f"{_BASE}/gauge/number/[",
    "]": f"{_BASE}/gauge/number/]",
    "/": f"{_BASE}/gauge/number/slash",
    "%": f"{_BASE}/gauge/number/%",
    ".": f"{_BASE}/gauge/number/.",
    ",": f"{_BASE}/gauge/number/,",
}
# The level has at most three digits; the strip holds a fourth, so a fourth
# digit is seen and refused instead of cut off.
_LEVEL_DIGIT_COUNT = 4

STATUS_BAR = Declaration(
    "status bar",
    canvases=(
        GAUGE_LABEL,
        BACKGROUND,
        *_LEVEL_DIGITS.values(),
        *_GAUGE_GLYPHS.values(),
    ),
    vectors=(_LEVEL_AT, _HP_AT, _MP_AT, _EXP_AT),
)

# Glyphs of one string are drawn a pixel apart (frames); a wider gap, or a string
# that doesn't start where its strip does, means a glyph isn't there to be read:
# something (the cursor, a window) is over it.
_MAX_GLYPH_GAP = 2
_DIGIT_SPACING = 1
_HP_MP = re.compile(r"\[(\d+)/(\d+)\]")
# The client groups the EXP in thousands: "2,869[6.08%]".
_EXP = re.compile(r"(\d{1,3}(?:,\d{3})*|\d+)\[(\d+(?:\.\d+)?)%\]")
_LEVEL = re.compile(r"\d{1,3}")


@dataclass(frozen=True, slots=True)
class StatusBar:
    """What the status bar shows. `exp_percent` is in percent, as drawn."""

    level: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    exp: int
    exp_percent: float


class StatusBarReader:
    """
    Reads the status bar from a `Frame`, remembering where it was.

    One per bot, built with the bot's shared `FrameCheck`.
    """

    def __init__(self, sprites: ReaderSprites, frame_check: FrameCheck) -> None:
        self._frame_check = frame_check
        self._background = sprites.canvas(BACKGROUND)
        self._level_glyphs = _glyphs(sprites, _LEVEL_DIGITS)
        self._gauge_glyphs = _glyphs(sprites, _GAUGE_GLYPHS)
        label = sprites.canvas(GAUGE_LABEL)
        level_w, level_h = _size(self._level_glyphs["0"])
        self._digit = (level_w, level_h)
        _, gauge_h = _size(self._gauge_glyphs["0"])
        level_x, level_y = sprites.vector(_LEVEL_AT)
        hp_x, hp_y = sprites.vector(_HP_AT)
        mp_x, mp_y = sprites.vector(_MP_AT)
        exp_x, exp_y = sprites.vector(_EXP_AT)
        # Where each string is drawn, from the bar's origin: from its vector to
        # the next number's, the last to the label's right edge.
        label_right = label.rgba.shape[1] - label.origin[0]
        self._strips = {
            # The digits of a two-digit level start one digit left of the vector
            # (frames); the strip starts there, so alignment of 1 and 3 digits is
            # unverified.
            "level": (
                level_x - level_w,
                level_y,
                level_w * (_LEVEL_DIGIT_COUNT + 1),
                level_h,
            ),
            "hp": (hp_x, hp_y, mp_x - hp_x, gauge_h),
            "mp": (mp_x, mp_y, exp_x - mp_x, gauge_h),
            "exp": (exp_x, exp_y, label_right - exp_x, gauge_h),
        }
        # The numbers are drawn over the bar's own sprites, so the pixels they
        # cover can't be compared: they are left out of what locates the bar.
        self.locator = Locator(
            self._part(label), (self._part(sprites.canvas(BACKGROUND)),)
        )

    def _part(self, sprite: Sprite) -> Part:
        """A part of the bar, without the pixels the numbers are drawn over."""
        part = Part(sprite)
        dx, dy = part.offset
        rgba = sprite.rgba.copy()
        for x, y, w, h in self._strips.values():
            rgba[
                max(y - dy, 0) : max(y + h - dy, 0),
                max(x - dx, 0) : max(x + w - dx, 0),
                3,
            ] = 0
        if not (rgba[:, :, 3] == 255).any():
            raise ValueError(f"{sprite.path} is entirely under the numbers")
        return Part(Sprite(sprite.path, rgba, sprite.origin))

    def read(self, frame: Frame) -> Reading[StatusBar]:
        """
        The status bar in `frame`. Never raises because of what is on screen.
        """
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        located = self.locator.locate(frame)
        missing = unreadable(located, frame)
        if missing is not None:
            return missing
        assert located is not None

        level = self._read_level(frame, located)
        hp = self._read_gauge(frame, located, "hp")
        mp = self._read_gauge(frame, located, "mp")
        exp = self._read_gauge(frame, located, "exp")

        level_match = _LEVEL.fullmatch(level)
        hp_match = _HP_MP.fullmatch(hp)
        mp_match = _HP_MP.fullmatch(mp)
        exp_match = _EXP.fullmatch(exp)
        for name, string, parsed in (
            ("level", level, level_match),
            ("hp", hp, hp_match),
            ("mp", mp, mp_match),
            ("exp", exp, exp_match),
        ):
            if parsed is None:
                detail = string.removeprefix("!")
                hidden = (
                    " (a glyph is missing or hidden)"
                    if string.startswith("!") and detail
                    else ""
                )
                return Reading.unsure(frame.captured_at, f"{name}: {detail!r}{hidden}")
        assert level_match
        assert hp_match
        assert mp_match
        assert exp_match
        return Reading.read(
            StatusBar(
                level=int(level_match.group()),
                hp=int(hp_match.group(1)),
                max_hp=int(hp_match.group(2)),
                mp=int(mp_match.group(1)),
                max_mp=int(mp_match.group(2)),
                exp=int(exp_match.group(1).replace(",", "")),
                exp_percent=float(exp_match.group(2)),
            ),
            frame.captured_at,
        )

    def _hits(
        self,
        frame: Frame,
        located: Located,
        name: str,
        glyphs: dict[str, NDArray[np.uint8]],
    ) -> tuple[list[GlyphHit], tuple[int, int]]:
        """The glyphs of a strip, and the strip's top-left in the frame."""
        x, y, w, h = self._strips[name]
        px, py = located.position((x, y))
        return find_glyphs(_crop(frame.pixels, px, py, w, h), glyphs), (px, py)

    def _read_gauge(self, frame: Frame, located: Located, name: str) -> str:
        """
        The string of an HP, MP or EXP strip, or a description of what is wrong
        with it, prefixed `!`. It starts at the strip's start and ends at its
        closing bracket: the strip runs on to the next number's label, whose
        letters match the small glyphs.
        """
        hits, _ = self._hits(frame, located, name, self._gauge_glyphs)
        closing = next((i for i, hit in enumerate(hits) if hit.name == "]"), None)
        if closing is not None:
            hits = hits[: closing + 1]
        text = "".join(hit.name for hit in hits)
        if not hits or hits[0].x > _MAX_GLYPH_GAP or _has_gap(hits):
            return f"!{text}"
        return text

    def _read_level(self, frame: Frame, located: Located) -> str:
        hits, (px, py) = self._hits(frame, located, "level", self._level_glyphs)
        text = "".join(hit.name for hit in hits)
        if not hits or _has_gap(hits):
            return f"!{text}"
        # The cells either side of the digits must show the bar's own background:
        # a digit hidden at either end leaves its cell showing what hides it.
        width, height = self._digit
        step = width + _DIGIT_SPACING
        for cell_x in (hits[0].x - step, hits[-1].x + step):
            if not self._shows_background(
                frame, located, (px + cell_x, py, width, height)
            ):
                return f"!{text}"
        return text

    def _shows_background(
        self,
        frame: Frame,
        located: Located,
        cell: tuple[int, int, int, int],
    ) -> bool:
        """Whether the bar's background sprite matches `cell`, where it is opaque.
        A cell with no opaque background pixel can't be judged, and passes."""
        sprite = self._background
        left, top = located.position(Part(sprite).offset)
        x, y, w, h = cell
        x0, y0 = max(x, left), max(y, top)
        x1 = min(x + w, left + sprite.rgba.shape[1], frame.pixels.shape[1])
        y1 = min(y + h, top + sprite.rgba.shape[0], frame.pixels.shape[0])
        if x1 <= x0 or y1 <= y0:
            return True
        rgba = sprite.rgba[y0 - top : y1 - top, x0 - left : x1 - left]
        opaque = rgba[:, :, 3] == 255
        if not opaque.any():
            return True
        shown = frame.pixels[y0:y1, x0:x1]
        return bool((shown[opaque] == rgba[:, :, 2::-1][opaque]).all())


def _has_gap(hits: list[GlyphHit]) -> bool:
    return any(
        later.x - (earlier.x + earlier.width) > _MAX_GLYPH_GAP
        for earlier, later in pairwise(hits)
    )


def _glyphs(
    sprites: ReaderSprites, paths: dict[str, str]
) -> dict[str, NDArray[np.uint8]]:
    return {name: sprites.canvas(path).rgba for name, path in paths.items()}


def _size(rgba: NDArray[np.uint8]) -> tuple[int, int]:
    return rgba.shape[1], rgba.shape[0]


def _crop(
    pixels: NDArray[np.uint8], x: int, y: int, w: int, h: int
) -> NDArray[np.uint8]:
    return pixels[max(y, 0) : y + h, max(x, 0) : x + w]
