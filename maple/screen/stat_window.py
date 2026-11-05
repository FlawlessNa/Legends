"""
The stat window (Character Stat): the AP left to spend, and speed and jump.

**Locating.** The window's Main panel is drawn from one point, its
`UI/CharacterStat.img/Main/backgrnd`'s; the Detail panel, opened by Main's
Detail button, from its own, `Detail/backgrnd`'s. Each panel's background
matches MSCW's screen exactly, except where the client draws over it (frame set
`v2`, `m_ability_*`): the values, the buttons, and, for Detail, its left edge
under Main. So each panel is located by its background with those parts left
out, cut in three:

- the anchor, the column of labels left of the values (`vector:name`'s x for
  Main, `vector:attack`'s for Detail);
- two fixed parts, above and below it: Main's title bar (less the close button)
  and its AP label, left of `vector:ap`; Detail's border above its values, and
  its bottom bar (less the hide button).

The three are apart enough that a block the cursor's size never hides them all,
so a covered panel is `COVERED`, never taken for a hidden one. A panel hidden
whole, under another window, is: Detail's speed and jump are then `None`, as if
it weren't open.

Where the values are drawn is given by `vector:` nodes and the buttons' origins.
`DETAIL_UNDER_MAIN` is the one measured number: how many of Detail's columns
Main covers.

**Reading.** Numbers are drawn in black, unantialiased, with the client's font,
and read with glyphs harvested from the frames (`font.STAT_WINDOW_GLYPHS`):

- AP, in the box from `Main/vector:ap` to the Detail button;
- speed and jump, from `Detail/vector:spd` and `vector:jmp`, each one value row
  tall (the rows are `vector:jmp - vector:spd` apart), only while Detail is
  shown: otherwise they are `None`.

A strip is compared with the panel's background: a pixel that is neither the
background nor black ink is something over the number (the cursor, a window),
and the reading is `COVERED`. Ink that no glyph explains, or a string that
doesn't parse, is `UNSURE`, with the string as `detail`.

**The +1 buttons agree with the AP.** The client disables STR, DEX, INT and LUK's
buttons when no AP is left. So an AP of 0 with any of them drawn enabled, or an
AP above 0 with all four drawn disabled, is `UNSURE`, never a value. Frame set
`v2` shows only an AP of 0, with the four buttons disabled; an AP above 0, and
the enabled buttons' look, haven't been seen.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from botting.screen import Frame, Reading, Status, find_mask_glyphs, matches_at
from game_data.sprites import Sprite

from .font import STAT_WINDOW_GLYPHS
from .locator import FrameCheck, Located, Locator, Part, unreadable
from .sprites import Declaration, ReaderSprites

_BASE = "UI/CharacterStat.img"
MAIN_BACKGROUND = f"{_BASE}/Main/backgrnd"
DETAIL_BACKGROUND = f"{_BASE}/Detail/backgrnd"
_NAME_AT = f"{_BASE}/Main/vector:name"
_AP_AT = f"{_BASE}/Main/vector:ap"
_ATTACK_AT = f"{_BASE}/Detail/vector:attack"
_SPEED_AT = f"{_BASE}/Detail/vector:spd"
_JUMP_AT = f"{_BASE}/Detail/vector:jmp"
_CLOSE = f"{_BASE}/Main/button:close/normal/0"
_DETAIL_BUTTON = f"{_BASE}/Main/button:detail/normal/0"
_HIDE = f"{_BASE}/Detail/button:hide/normal/0"

STATS = ("STR", "DEX", "INT", "LUK")
"""The stats AP is spent on, as `Character.main_stat` names them."""
_DISABLED = "disabled"
_ENABLED = ("normal", "mouseOver")


def _up_button(stat: str, state: str) -> str:
    return f"{_BASE}/Main/button:{stat.lower()}up/{state}/0"


STAT_WINDOW = Declaration(
    "stat window",
    canvases=(
        MAIN_BACKGROUND,
        DETAIL_BACKGROUND,
        _CLOSE,
        _DETAIL_BUTTON,
        _HIDE,
        *(
            _up_button(stat, state)
            for stat in STATS
            for state in (_DISABLED, *_ENABLED)
        ),
    ),
    vectors=(_NAME_AT, _AP_AT, _ATTACK_AT, _SPEED_AT, _JUMP_AT),
    glyph_sets=(STAT_WINDOW_GLYPHS.name,),
)

DETAIL_UNDER_MAIN = 4
"""Detail's leftmost columns, which Main is drawn over: a shadow that never shows.
Measured on frame set `v2` (`m_ability_open_1920x1080`), where Main's right edge
covers Detail's first 4 columns."""

_AP = re.compile(r"0|[1-9]\d{0,2}")
_PERCENT = re.compile(r"([1-9]\d{1,2})%")

type Rect = tuple[int, int, int, int]
"""`(x, y, width, height)`, relative to a panel's point."""


@dataclass(frozen=True, slots=True)
class StatWindow:
    """
    What the stat window shows.

    :ivar available_ap: The AP left to spend.
    :ivar speed: Speed, in percent as drawn, or `None` when Detail isn't shown.
    :ivar jump: Jump, likewise.
    :ivar up_buttons: Each stat's +1 button's centre, in client pixels.
    """

    available_ap: int
    speed: int | None
    jump: int | None
    up_buttons: Mapping[str, tuple[int, int]]


class StatWindowReader:
    """
    Reads the stat window from a `Frame`, remembering where each panel was.

    One per bot, built with the bot's shared `FrameCheck`.

    :ivar glyphs: The harvested glyphs it reads numbers with.
    """

    def __init__(self, sprites: ReaderSprites, frame_check: FrameCheck) -> None:
        self._frame_check = frame_check
        self.glyphs = sprites.glyph_set(STAT_WINDOW_GLYPHS.name).glyphs
        main = sprites.canvas(MAIN_BACKGROUND)
        detail = sprites.canvas(DETAIL_BACKGROUND)
        self._main, self._detail = main, detail
        main_box = _box(main)
        detail_box = _box(detail)
        close = _box(sprites.canvas(_CLOSE))
        hide = _box(sprites.canvas(_HIDE))
        name_x, name_y = sprites.vector(_NAME_AT)
        ap_x, ap_y = sprites.vector(_AP_AT)
        attack_x, attack_y = sprites.vector(_ATTACK_AT)
        speed_x, speed_y = sprites.vector(_SPEED_AT)
        jump_x, jump_y = sprites.vector(_JUMP_AT)
        row = jump_y - speed_y
        detail_button = _box(sprites.canvas(_DETAIL_BUTTON))

        # Main: the labels' column; the title bar above it; the AP's label below
        # it. A block the cursor's size can't hide all three.
        left, top, width, height = main_box
        bottom = top + height
        self._ap_strip: Rect = (ap_x, ap_y, detail_button[0] - ap_x, bottom - ap_y)
        self.main_locator = Locator(
            _cut(main, (left, name_y, name_x - left, ap_y - name_y), (), "labels"),
            (
                _cut(main, (left, top, width, name_y - top), (close,), "title bar"),
                _cut(main, (left, ap_y, ap_x - left, bottom - ap_y), (), "AP label"),
            ),
        )

        # Detail: the labels' column, the border above the values, and the bar
        # below them.
        left, top, width, height = detail_box
        right, bottom = left + width, top + height
        values_bottom = jump_y + row
        values: Rect = (attack_x, attack_y, right - attack_x, values_bottom - attack_y)
        self._speed_strip: Rect = (speed_x, speed_y, right - speed_x, row)
        self._jump_strip: Rect = (jump_x, jump_y, right - jump_x, row)
        shown = left + DETAIL_UNDER_MAIN
        self.detail_locator = Locator(
            _cut(
                detail,
                (shown, attack_y, attack_x - shown, values_bottom - attack_y),
                (),
                "labels",
            ),
            (
                _cut(detail, (shown, top, right - shown, attack_y - top), (), "top"),
                _cut(
                    detail,
                    (shown, values_bottom, right - shown, bottom - values_bottom),
                    (values, hide),
                    "bottom bar",
                ),
            ),
        )

        for panel, strip in (
            (main, self._ap_strip),
            (detail, self._speed_strip),
            (detail, self._jump_strip),
        ):
            if not _inside(strip, _box(panel)):
                raise ValueError(f"a value's strip {strip} isn't inside {panel.path}")

        self._up_parts = {
            stat: {
                state: Part(sprites.canvas(_up_button(stat, state)))
                for state in (_DISABLED, *_ENABLED)
            }
            for stat in STATS
        }

    def shown(self, frame: Frame) -> bool | None:
        """
        Whether the window is open in `frame`, whole or covered, whatever its
        numbers read: `None` when the frame can't be read.
        """
        if self._frame_check.frame_usable(frame) is not None:
            return None
        return self.main_locator.locate(frame) is not None

    def read(self, frame: Frame) -> Reading[StatWindow]:
        """
        The stat window in `frame`. Never raises because of what is on screen.
        """
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        main = self.main_locator.locate(frame)
        missing = unreadable(main, frame)
        if missing is not None:
            return missing
        assert main is not None

        ap_text, problem = self._text(frame, main, self._main, self._ap_strip)
        if problem is not None:
            return _not_read(problem, frame, f"AP: {ap_text}")
        if _AP.fullmatch(ap_text) is None:
            return Reading.unsure(frame.captured_at, f"AP: {ap_text!r}")
        ap = int(ap_text)
        disabled = self._disabled(frame, main)
        if ap == 0 and disabled is not True:
            return Reading.unsure(
                frame.captured_at, "AP: 0, but a +1 button is drawn enabled"
            )
        if ap > 0 and disabled is True:
            return Reading.unsure(
                frame.captured_at, f"AP: {ap}, but every +1 button is drawn disabled"
            )

        speed = jump = None
        detail = self.detail_locator.locate(frame, self._beside(main))
        if detail is not None:
            covered = unreadable(detail, frame)
            if covered is not None:
                return Reading.covered(frame.captured_at, f"Detail: {covered.detail}")
            values: list[int] = []
            for name, strip in (
                ("speed", self._speed_strip),
                ("jump", self._jump_strip),
            ):
                text, problem = self._text(frame, detail, self._detail, strip)
                if problem is not None:
                    return _not_read(problem, frame, f"{name}: {text}")
                parsed = _PERCENT.fullmatch(text)
                if parsed is None:
                    return Reading.unsure(frame.captured_at, f"{name}: {text!r}")
                values.append(int(parsed.group(1)))
            speed, jump = values

        return Reading.read(
            StatWindow(ap, speed, jump, self._up_centres(main)), frame.captured_at
        )

    def _text(
        self, frame: Frame, located: Located, background: Sprite, strip: Rect
    ) -> tuple[str, Status | None]:
        """
        The text drawn in `strip` over `background`; or what is wrong with it,
        with the status to read instead (`COVERED` or `UNSURE`).
        """
        x, y, w, h = strip
        px, py = located.position((x, y))
        frame_h, frame_w = frame.pixels.shape[:2]
        if px < 0 or py < 0 or px + w > frame_w or py + h > frame_h:
            return "off the frame", Status.COVERED
        shown = frame.pixels[py : py + h, px : px + w].astype(np.int16)
        dx, dy = Part(background).offset
        rgba = background.rgba[y - dy : y - dy + h, x - dx : x - dx + w]
        opaque = rgba[:, :, 3] == 255
        under = rgba[:, :, 2::-1].astype(np.int16)  # RGB -> BGR, as captured
        black = (shown == 0).all(axis=2)
        ink = opaque & black & ~(under == 0).all(axis=2)
        foreign = opaque & ~ink & (shown != under).any(axis=2)
        if foreign.any():
            return f"{int(foreign.sum())} pixel(s) over it", Status.COVERED
        hits = find_mask_glyphs(ink, self.glyphs, STAT_WINDOW_GLYPHS.max_error)
        text = "".join(hit.name for hit in hits)
        explained = sum(int(self.glyphs[hit.name].sum()) for hit in hits)
        if explained != int(ink.sum()):
            return f"{text!r} and ink no glyph explains", Status.UNSURE
        return text, None

    def _beside(self, main: Located) -> Rect:
        """
        Where Detail can be, in client pixels: touching Main, since it opens
        from Main's Detail button. Searching only there keeps a hidden Detail
        from costing a search of the whole frame on every read.
        """
        x, y, w, h = _box(self._main)
        _, _, detail_w, detail_h = _box(self._detail)
        left, top = main.position((x, y))
        return (left - detail_w, top - detail_h, w + 2 * detail_w, h + 2 * detail_h)

    def _disabled(self, frame: Frame, located: Located) -> bool | None:
        """
        `True` when all four +1 buttons are drawn disabled, `False` when any is
        drawn enabled, `None` when neither can be told (something over them).
        """
        states = [
            next(
                (
                    state
                    for state, part in parts.items()
                    if matches_at(frame.pixels, part.sprite.rgba, *_at(located, part))
                ),
                None,
            )
            for parts in self._up_parts.values()
        ]
        if any(state in _ENABLED for state in states):
            return False
        if all(state == _DISABLED for state in states):
            return True
        return None

    def _up_centres(self, located: Located) -> dict[str, tuple[int, int]]:
        centres: dict[str, tuple[int, int]] = {}
        for stat, parts in self._up_parts.items():
            part = parts[_DISABLED]
            x, y = _at(located, part)
            h, w = part.sprite.rgba.shape[:2]
            centres[stat] = (x + w // 2, y + h // 2)
        return centres


def _not_read(status: Status, frame: Frame, detail: str) -> Reading[StatWindow]:
    if status is Status.COVERED:
        return Reading.covered(frame.captured_at, detail)
    return Reading.unsure(frame.captured_at, detail)


def _at(located: Located, part: Part) -> tuple[int, int]:
    """Where `part`'s top-left is, in client pixels."""
    return located.position(part.offset)


def _box(sprite: Sprite) -> Rect:
    """A sprite's box, relative to the point it is drawn from."""
    dx, dy = Part(sprite).offset
    return dx, dy, sprite.rgba.shape[1], sprite.rgba.shape[0]


def _cut(sprite: Sprite, keep: Rect, holes: tuple[Rect, ...], name: str) -> Part:
    """
    A part of `sprite`: only its pixels inside `keep` and outside `holes`, all
    relative to the point it is drawn from, cut to `keep`, so a panel partly off
    the frame is still found by the part that is on it. Its path names the part.
    """
    dx, dy = Part(sprite).offset
    alpha = np.zeros(sprite.rgba.shape[:2], bool)
    alpha[_slices(keep, dx, dy)] = True
    for hole in holes:
        alpha[_slices(hole, dx, dy)] = False
    rgba = sprite.rgba.copy()
    rgba[~alpha, 3] = 0
    rows, columns = _slices(keep, dx, dy)
    rgba = rgba[rows, columns]
    if not (rgba[:, :, 3] == 255).any():
        raise ValueError(f"{sprite.path} has no opaque pixel in its {name}")
    origin = (sprite.origin[0] - columns.start, sprite.origin[1] - rows.start)
    return Part(Sprite(f"{sprite.path} ({name})", rgba, origin))


def _inside(rect: Rect, box: Rect) -> bool:
    x, y, w, h = rect
    bx, by, bw, bh = box
    return (
        w > 0
        and h > 0
        and bx <= x
        and by <= y
        and x + w <= bx + bw
        and y + h <= by + bh
    )


def _slices(rect: Rect, dx: int, dy: int) -> tuple[slice, slice]:
    x, y, w, h = rect
    return (
        slice(max(y - dy, 0), max(y - dy + h, 0)),
        slice(max(x - dx, 0), max(x - dx + w, 0)),
    )
