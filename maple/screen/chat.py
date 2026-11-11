"""
The chat: its log split into lines, each line's kind, and the new lines since
the last read.

**Locating.** The chat is drawn from one point, the point `UI/StatusBar.img/chat`
is drawn from. It is found by `chat/button:ChatTargetSelect/normal/0` (the "All"
button) with its label masked out, since the label changes with the chat target,
and by the log's toggle beside it, `button:ChatLogMin/normal/0` while the log is
shown, `button:ChatLogMax/normal/0` while it is hidden. Both are placed by their
origins, and both match MSCW's screen exactly (frame set `v1`, f001).

**MSCW draws its own log.** The classic log's sprites (`chatbackgrnd2`,
`chatedit`) don't match the screen anywhere, and `chatlog_lt` (20, 12) and
`chatlog_rb` (520, 29) don't bound MSCW's log: they lie across the input bar,
which the log sits above. So the log is placed by the one log sprite MSCW still
draws, the scroll bar's up arrow `chat/VScr/enabled/prev0`, whose top is the
log's top, and by these offsets from the chat's point, measured on frame set
`v1` and `v2` at 800x600, 1024x768, 1280x720, 1366x768 and 1920x1080:

- the rows end `LOG_BOTTOM` below the point, and are `ROW_HEIGHT` tall, packed
  from the bottom: as many as fit under the arrow (4 in `v1`; 6 in `v2`'s `j_*`
  frames, whose log is taller);
- a row's band runs from `BAND_LEFT` to `BAND_RIGHT`, and the arrow is drawn at
  `SCROLL_X`;
- a row's text is drawn from `BAND_LEFT + 2` to `BAND_RIGHT - 5` at most, so the
  band's two ends (`_END`) show only the row's own background.

**Covered.** A row's background is read at its two ends, which must agree, and
along its gap row (`_GAP_ROW`), which no text crosses, so a run of it longer
than `COVER_RUN` that doesn't show the background is something over the row.
Either makes the reading `COVERED`: in the frame set, every window or notice
over the log did (f031-f033, f045, f047, f048, f050-f052). The cursor is
narrower than `COVER_RUN`, and is caught only over a row's end.

**Kinds.** Then:

- a band of one of `MEGAPHONE_BANDS` is a megaphone. A band is translucent, so
  the map behind it moves its colour: each band is known by its colour over the
  darkest and the brightest map seen (`Band`);
- no band (the log's backdrop, black at half opacity over the game, so never
  brighter than `BACKDROP_MAX`) with all its text white is general, and all
  yellow, or the light blue of an event's notice, is system (`TEXT_COLOURS`);
- a row with no band and no text is empty, and isn't a line;
- anything else is `unknown`: party, buddy, whisper and GM lines haven't been
  captured (frame set `v3` has none), so their colours aren't known, and they
  read `unknown` until frames of them are in the set (#456). So does a
  megaphone band not seen yet.

The mouse cursor over a row's text (`cursor.CURSOR_PATHS`) is none of the
row's: when a row's text isn't of one kind, the cursor is looked for, and the
pixels it is drawn over are left out of the row's kind and its signature. In
its text, what the cursor hides reads `UNREAD`, one for each run of columns it
covers, text or not.

A line that wraps is one row per screen row, each with the kind of its colours.

**Text** is read for general lines, with the white glyphs harvested from the
frames (`font.CHAT_GENERAL`, #313, #456), in each row's 14-row glyph cell, 3
rows below its top. A letter with no glyph reads `UNREAD` (U+FFFD) in its place
(`GlyphSet.read_marked`), so a partly read line keeps its kind and the rest of
its text. Frame set `v3` holds 52 of the 95 printable characters in white, the
space among them (`toolkit/glyph_sources/v3.json`); the others read `UNREAD`
until frames of them are harvested. Arial draws `I` and `l` alike, so both read
`I` (`ALIKE`). The log fades out over its last rows of pixels (`FADE`), which
the newest line's baseline and descenders are drawn in: the fade is undone
before its glyphs are read.
System, party, buddy, whisper and GM text waits for those colours' glyphs.

**Speaker and message** are split from a general line's text by its format,
`Name : message`, read on frame sets `v1` (f001-f005) and `v3`, where the client
puts the time before it: `[16:22] Name : message`. A name is letters and digits
(or `UNREAD`). A row that doesn't fit, the second row of a wrapped line among
them, has neither. A line is `outgoing` when its speaker reads as the
character's own name (`reads_as`, ignoring case); the outgoing whisper's format
waits for a frame of one.

**New lines.** Each row has a signature: which of its pixels are text. A read
compares the rows with the previous read's: the log scrolls up as lines arrive,
so the new lines are the bottom rows that the previous rows, shifted up the
fewest rows, don't explain. A line repeated exactly, as many times as the log
has rows, can't be told from no new line.
"""

import enum
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from botting.screen import Frame, Reading, match, matches_at
from botting.utilities import Box
from game_data.sprites import Sprite

from .cursor import CURSOR_PATHS, cursor_mask
from .font import CHAT_GENERAL, UNREAD, GlyphSet
from .locator import FrameCheck, Located, Locator, Part
from .sprites import Declaration, ReaderSprites

_CHAT = "UI/StatusBar.img/chat"
TARGET_SELECT = f"{_CHAT}/button:ChatTargetSelect/normal/0"
SCROLL_UP = f"{_CHAT}/VScr/enabled/prev0"
LOG_SHOWN = "UI/StatusBar.img/button:ChatLogMin/normal/0"
LOG_HIDDEN = "UI/StatusBar.img/button:ChatLogMax/normal/0"

CHAT = Declaration(
    "chat",
    canvases=(TARGET_SELECT, SCROLL_UP, LOG_SHOWN, LOG_HIDDEN, *CURSOR_PATHS),
    glyph_sets=(CHAT_GENERAL.name,),
)

# The target button's label: the rows and columns it may be drawn in, masked out
# of the anchor. The border and the arrow at its left are kept.
_LABEL_ROWS = (2, 16)
_LABEL_COLUMNS = (10, 72)

# Offsets from the chat's point, measured on the frame set (module docstring).
LOG_BOTTOM = 3
ROW_HEIGHT = 16
BAND_LEFT = 11
BAND_RIGHT = 552
SCROLL_X = 555
_END = 2
"""Columns read at each end of a row for its background."""
_CELL_TOP = 3
"""A row's glyph cell starts this many rows below its top (`font.CHAT_GENERAL`)."""
_GAP_ROW = 2
"""A row's third pixel row holds no text: its own starts below it, and the line
above's descenders end above it. Only the channel badges of megaphones cross it."""
COVER_RUN = 80
"""More columns than this in a run, along a row's gap row, that don't show its
background, are something over the log. In the frame set, a row's own badges
crossed at most 60 in a run (36 on the labelled frames), and every window over
the log 124 or more (f031, f045, f047). A cursor is narrower, and isn't caught
unless it covers a row's end."""

type RGB = tuple[int, int, int]


class ChatKind(enum.Enum):
    GENERAL = "general"
    PARTY = "party"
    BUDDY = "buddy"
    WHISPER = "whisper"
    GM = "gm"
    MEGAPHONE = "megaphone"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Band:
    """
    A megaphone band's colour, in RGB, over the darkest and the brightest map
    it was read on. The band is drawn translucent, so the game behind it shows
    through: its row ends read anywhere between the two.
    """

    dark: RGB
    bright: RGB
    seen: str
    """The frames each end was read from."""


MEGAPHONE_BANDS: dict[str, Band] = {
    "yellow": Band((221, 172, 0), (238, 189, 17), "f022 row 3 (v1); ellinia_042 (v3)"),
    "pink": Band((204, 153, 177), (229, 178, 202), "f024 row 1 (v1); ellinia_036 (v3)"),
    "teal": Band((81, 207, 191), (98, 224, 208), "f012 row 1 (v1); ellinia_038 (v3)"),
    "light blue": Band(
        (142, 162, 179), (175, 195, 214), "f001 row 4 (v1); henesyscrowd_030 (v3)"
    ),
    "red": Band(
        (138, 60, 49),
        (187, 105, 106),
        "j_1280x720_pagedown_3 and _4 (v2); henesyscrowd_000 (v3)",
    ),
}
"""Each megaphone band, by its colour's name. The red band carries the client's
announcements of what a player obtained from a crate, a broadcast like the
megaphones'. Over the game, yellow, pink and teal brighten by 17 levels from
their darkest to their brightest, light blue by 33 and red by about 50: the
more translucent a band, the more the map behind it moves it."""
BAND_TOLERANCE = 24
"""How far, per channel, a row's end may be from a band, between its dark and
bright colours, and still be that band; the nearest band, when two are in
reach. A band's ends in the frame set were within 11 of it; two bands are 46 or
more apart (pink and light blue)."""
BACKDROP_MAX = 127
"""A row end with no channel above this is the log's backdrop, not a band. The
backdrop is black drawn at half opacity over the game, so no pixel of it is
brighter than 127: in the frame set, its brightest pixel read 127, over Henesys,
and the darkest band end 132 (red, over Ellinia). A band darker than this would
be taken for the backdrop, and its row read `unknown`: its text isn't one of
`TEXT_COLOURS` alone. On the backdrop, a pixel with a channel above this is
text."""
INK_MIN = 200
TEXT_COLOURS: dict[RGB, ChatKind] = {
    (255, 255, 255): ChatKind.GENERAL,  # f001 rows 2-3 (v1)
    (255, 255, 0): ChatKind.SYSTEM,  # f065 rows 3-4 (v1)
    (96, 206, 255): ChatKind.SYSTEM,  # an event's notice: henesys_1366x768_08 (v3)
}
"""The text colours of the rows on the backdrop, and the kind of line each is.
A text pixel is one of these colours dimmed, by `FADE` at the log's bottom, to
a brightest channel no lower than `INK_MIN`, within `COLOUR_TOLERANCE`."""
COLOUR_TOLERANCE = 6
"""How far, per channel, a text pixel may be from its colour, dimmed as bright
as the pixel. The text is drawn unantialiased: in the frame set, every pixel of
a line was its colour exactly, or dimmed by the fade."""
FADE = (251, 243, 231, 214)
"""The log fades out at its bottom: its last three rows of pixels, and the one
below them that the bottom row's descenders reach (`LOG_BOTTOM`), draw white as
these, top to bottom, and every colour by as much. Measured on every frame of
the set, at every client size; the log's top doesn't fade."""
_SIGNATURE_DIFFERENCE = 48
"""On a band, a pixel more than this from the band's colour, in any channel,
is text, for the row's signature."""


ALIKE: dict[str, str] = {"I": "Il"}
"""Letters the chat's font, Arial at 14 px, draws alike: the one a line reads ->
every letter it may be (`toolkit.harvest_glyphs.alike`; a `frames` test checks
the harvested set says the same)."""

_GENERAL_FORMAT = re.compile(
    rf"(?:\[[^\]]*\] )?(?P<speaker>[A-Za-z0-9{UNREAD}]+) : (?P<message>.+)"
)
"""A general line: the time the client may put first, the speaker, then the
message (module docstring)."""


def reads_as(read: str, written: str, *, ignore_case: bool = False) -> bool:
    """
    Whether chat text read as `read` may be `written`: as long, and equal letter
    by letter, where `UNREAD` may be any letter and a letter of `ALIKE` any of
    those drawn like it.
    """
    if len(read) != len(written):
        return False
    for r, w in zip(read, written, strict=True):
        if r == UNREAD:
            continue
        could_be = ALIKE.get(r, r)
        if ignore_case:
            if w.casefold() not in {c.casefold() for c in could_be}:
                return False
        elif w not in could_be:
            return False
    return True


@dataclass(frozen=True, eq=False, slots=True)
class ChatLine:
    """
    One row of the chat log.

    :ivar kind: What kind of line it is, from its colours.
    :ivar image: The row, as captured (`H x W x 3`, BGR).
    :ivar text: What it says, for the kinds whose glyphs are harvested (general,
        for now), with `UNREAD` for each letter that has no glyph; `None` for
        the other kinds.
    :ivar top: The row's top, in client pixels.
    :ivar speaker: Who wrote it, split from `text` by its kind's format; `None`
        when the kind has none known, or the row doesn't fit it. On an outgoing
        whisper, it is whom the whisper went to, not the character: the relay
        reads it as `you · whisper to <speaker>` (#462). No whisper is read yet.
    :ivar message: What they wrote, split the same way; `None` with `speaker`.
    :ivar outgoing: The character sent it: its speaker reads as the
        character's name.
    """

    kind: ChatKind
    image: NDArray[np.uint8]
    text: str | None
    top: int
    speaker: str | None = None
    message: str | None = None
    outgoing: bool = False


@dataclass(frozen=True, slots=True)
class _Row:
    kind: ChatKind | None
    """`None` for an empty row."""
    signature: bytes
    image: NDArray[np.uint8] = field(compare=False)
    top: int = field(compare=False)
    under_cursor: bool = field(default=False, compare=False)
    """The mouse cursor is drawn over its text."""


class ChatReader:
    """
    Reads the chat. One per bot, sharing its `FrameCheck`.

    It remembers where the chat was, and the rows it saw last, so `read` returns
    only the lines that are new since its previous `read`. Given the
    character's name, `ign`, it tells the lines the character sent; without it,
    no line is `outgoing`.
    """

    def __init__(
        self,
        sprites: ReaderSprites,
        frame_check: FrameCheck,
        tolerance: float = 0.5,
        ign: str | None = None,
    ) -> None:
        self._frame_check = frame_check
        self._ign = ign
        self._tolerance = tolerance
        target = sprites.canvas(TARGET_SELECT)
        rgba = target.rgba.copy()
        rgba[slice(*_LABEL_ROWS), slice(*_LABEL_COLUMNS), 3] = 0
        self._shown = Part(sprites.canvas(LOG_SHOWN))
        self._hidden = Part(sprites.canvas(LOG_HIDDEN))
        self._scroll_up = sprites.canvas(SCROLL_UP)
        self._target = Part(Sprite(target.path, rgba, target.origin))
        self._bar_bottom = target.rgba.shape[0] - target.origin[1]
        self._glyphs: GlyphSet = sprites.glyph_set(CHAT_GENERAL.name)
        self._cursors = [sprites.canvas(path).rgba for path in CURSOR_PATHS]
        self.locator = Locator(self._target, (self._shown,), tolerance)
        self._previous: list[_Row] | None = None

    # The chat's state.

    def shown(self, frame: Frame) -> Reading[bool]:
        """
        Whether the chat log is shown. `False` when the log is hidden, or the
        chat isn't drawn at all while the rest of the UI is.
        """
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        located = self.locator.locate(frame)
        if located is None:
            return Reading.read(False, frame.captured_at, "chat not drawn")
        state = self._log_state(frame, located)
        if state is None:
            return Reading.covered(frame.captured_at, _COVERED_TOGGLE)
        return Reading.read(state, frame.captured_at)

    def region(self, frame: Frame) -> Box | None:
        """
        The chat, log included when it is shown, in client pixels; `None` when
        it isn't found whole. For readers of the play area to leave out.
        """
        if self._frame_check.frame_usable(frame) is not None:
            return None
        located = self.locator.locate(frame)
        if located is None or not located.anchor.matched:
            return None
        x, y = located.point
        top = y + LOG_BOTTOM
        if self._log_state(frame, located):
            arrow = self._find_scroll_up(frame, located)
            if arrow is not None:
                top = arrow
        return Box(
            left=x,
            right=x + SCROLL_X + self._scroll_up.rgba.shape[1],
            top=top,
            bottom=y + self._bar_bottom,
        )

    # The lines.

    def read(self, frame: Frame) -> Reading[list[ChatLine]]:
        """
        The lines new since the previous `read`, top to bottom. The first read
        returns every line shown. Never raises because of what is on screen.

        `ABSENT` when the chat or its log isn't shown; `COVERED` when something
        is over the log, its arrow or the chat's buttons. Neither changes what
        the next read compares with.
        """
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        located = self.locator.locate(frame)
        if located is None:
            return Reading.absent(frame.captured_at, "chat not found")
        if not located.anchor.matched:
            return Reading.covered(
                frame.captured_at, f"not where expected: {TARGET_SELECT}"
            )
        state = self._log_state(frame, located)
        if state is None:
            return Reading.covered(frame.captured_at, _COVERED_TOGGLE)
        if not state:
            return Reading.absent(frame.captured_at, "chat log hidden")
        arrow = self._find_scroll_up(frame, located)
        if arrow is None:
            return Reading.covered(frame.captured_at, f"log top not found: {SCROLL_UP}")
        x = located.point[0]
        bottom = located.point[1] + LOG_BOTTOM
        cursor = _Cursor(frame.pixels, self._cursors, x, arrow, bottom, self._tolerance)
        rows: list[_Row] = []
        for top in self._row_tops(located, arrow):
            row = self._row(frame.pixels, x, top, cursor)
            if isinstance(row, str):
                return Reading.covered(frame.captured_at, row)
            rows.append(row)
        new = _new_rows(self._previous, rows)
        self._previous = rows
        return Reading.read(
            [self._line(frame.pixels, x, row, bottom, cursor) for row in new],
            frame.captured_at,
        )

    def forget(self) -> None:
        """Forget the rows seen, so the next `read` returns every line shown."""
        self._previous = None

    # Helpers.

    def _log_state(self, frame: Frame, located: Located) -> bool | None:
        """`True` when the log's toggle says it is shown, `False` hidden, `None`
        when neither toggle is where it should be."""
        if located.parts[0].matched:
            return True
        part = located.parts[0]
        hidden = self._hidden.sprite
        if matches_at(frame.pixels, hidden.rgba, part.x, part.y, self._tolerance):
            return False
        return None

    def _find_scroll_up(self, frame: Frame, located: Located) -> int | None:
        """The log's top, in client pixels: the up arrow's top nearest the bar,
        in the arrow's column above the chat's point."""
        x, y = located.point
        arrow = self._scroll_up.rgba
        height, width = arrow.shape[:2]
        column = (x + SCROLL_X, 0, width, y + LOG_BOTTOM)
        hits = match(frame.pixels, arrow, column, self._tolerance)
        tops = [hit.y for hit in hits if y + LOG_BOTTOM - hit.y >= height]
        return max(tops) if tops else None

    def _row_tops(self, located: Located, log_top: int) -> list[int]:
        bottom = located.point[1] + LOG_BOTTOM
        count = (bottom - log_top) // ROW_HEIGHT
        return [bottom - ROW_HEIGHT * (count - i) for i in range(count)]

    def _row(
        self, pixels: NDArray[np.uint8], x: int, top: int, cursor: _Cursor
    ) -> _Row | str:
        """A row of the log, or why it can't be read."""
        left, right = x + BAND_LEFT, x + BAND_RIGHT
        image = pixels[top : top + ROW_HEIGHT, max(left, 0) : right]
        if left < 0 or image.shape[:2] != (ROW_HEIGHT, right - left):
            return f"the log's row at y={top} is off the frame"
        background = _background(image[:, :_END])
        if background != _background(image[:, -_END:]):
            return f"something is over the log's row at y={top}"
        pixels16 = image.astype(np.int16)
        # The row's own text: its top rows hold the descenders of the line above.
        own = pixels16[_CELL_TOP:]
        if background == _BACKDROP:
            gap = pixels16[_GAP_ROW].max(axis=1) > BACKDROP_MAX
            if _longest_run(gap) > COVER_RUN:
                return f"something is over the log's row at y={top}"
            ink = own.max(axis=2) > BACKDROP_MAX
            under = np.zeros_like(ink)
            if ink.any() and _text_kind(own[ink]) is ChatKind.UNKNOWN:
                # The cursor, drawn over the text, isn't the line's.
                under = cursor.over(top + _CELL_TOP, top + ROW_HEIGHT)
                ink &= ~under
            if not ink.any():
                return _Row(None, b"", image, top)
            kind = _text_kind(own[ink])
            signature = kind.value.encode() + np.packbits(ink).tobytes()
            return _Row(kind, signature, image, top, bool(under.any()))
        elif background is None:
            # Ends that agree on no known band are a band not seen yet, or
            # something drawn across the whole row: `unknown` either way.
            colour = _median(image[:, :_END])
            gap = _off(pixels16[_GAP_ROW : _GAP_ROW + 1], colour, BAND_TOLERANCE)
            if _longest_run(gap[0]) > COVER_RUN:
                return f"something is over the log's row at y={top}"
            ink = _off(own, colour, _SIGNATURE_DIFFERENCE)
            kind = ChatKind.UNKNOWN
        else:
            band = MEGAPHONE_BANDS[background]
            gap = _off_band(pixels16[_GAP_ROW : _GAP_ROW + 1], band) > BAND_TOLERANCE
            if _longest_run(gap[0]) > COVER_RUN:
                return f"something is over the log's row at y={top}"
            ink = _off_band(own, band) > _SIGNATURE_DIFFERENCE
            kind = ChatKind.MEGAPHONE
        return _Row(kind, kind.value.encode() + np.packbits(ink).tobytes(), image, top)

    def _line(
        self,
        pixels: NDArray[np.uint8],
        x: int,
        row: _Row,
        bottom: int,
        cursor: _Cursor,
    ) -> ChatLine:
        assert row.kind is not None
        if row.kind is not ChatKind.GENERAL:
            return ChatLine(row.kind, row.image.copy(), None, row.top)
        cell_top = row.top + _CELL_TOP
        cell_bottom = cell_top + (CHAT_GENERAL.rows or ROW_HEIGHT)
        cell = _unfaded(
            pixels[cell_top:cell_bottom, x + BAND_LEFT : x + BAND_RIGHT],
            cell_top,
            bottom,
        )
        if row.under_cursor:
            # What the cursor hides reads `UNREAD`, never as nothing.
            cell[cursor.over(cell_top, cell_bottom)] = 255
        text = self._glyphs.read_marked(cell)
        split = _GENERAL_FORMAT.fullmatch(text)
        if split is None:
            return ChatLine(row.kind, row.image.copy(), text, row.top)
        speaker = split["speaker"]
        return ChatLine(
            row.kind,
            row.image.copy(),
            text,
            row.top,
            speaker,
            split["message"],
            self._ign is not None and reads_as(speaker, self._ign, ignore_case=True),
        )


_COVERED_TOGGLE = (
    f"neither {LOG_SHOWN} nor {LOG_HIDDEN} is where expected: something is over it"
)


def _median(pixels: NDArray[np.uint8]) -> NDArray[np.int16]:
    """The median colour of `pixels` (BGR), as RGB."""
    return np.median(pixels.reshape(-1, 3), axis=0).astype(np.int16)[::-1]


_BACKDROP = "backdrop"


def _background(end: NDArray[np.uint8]) -> str | None:
    """
    What a row's end shows: `_BACKDROP` for the log's backdrop, a megaphone
    band's name, or `None` for any other colour.
    """
    colour = _median(end)
    if int(colour.max()) <= BACKDROP_MAX:
        return _BACKDROP
    bgr = colour[::-1].reshape(1, 3)
    off = {name: int(_off_band(bgr, band)[0]) for name, band in MEGAPHONE_BANDS.items()}
    nearest = min(off, key=lambda name: off[name])
    return nearest if off[nearest] <= BAND_TOLERANCE else None


def _off_band(image: NDArray[np.int16], band: Band) -> NDArray[np.int16]:
    """
    How far each pixel of `image` (`... x 3`, BGR) is from `band`: the largest
    difference, over the channels, from the nearest colour between its dark and
    bright ones.
    """
    dark = np.array(band.dark[::-1], np.float64)
    span = np.array(band.bright[::-1], np.float64) - dark
    along = np.clip(((image - dark) @ span) / (span @ span), 0.0, 1.0)
    nearest = dark + along[..., np.newaxis] * span
    return np.abs(image - nearest).max(axis=-1).round().astype(np.int16)


def _unfaded(cell: NDArray[np.uint8], cell_top: int, bottom: int) -> NDArray[np.uint8]:
    """
    A copy of `cell`, whose first row is at `cell_top`, with the log's `FADE`
    undone in the rows it dims, so that its text is drawn in its own colour
    again. `bottom` is where the log's rows end (`LOG_BOTTOM`).
    """
    cell = cell.copy()
    first = bottom - len(FADE) + 1
    for i, level in enumerate(FADE):
        y = first + i - cell_top
        if 0 <= y < cell.shape[0]:
            scaled = cell[y].astype(np.float64) * 255 / level
            cell[y] = np.clip(scaled.round(), 0, 255).astype(np.uint8)
    return cell


def _off(
    image: NDArray[np.int16], colour: NDArray[np.int16], tolerance: int
) -> NDArray[np.bool_]:
    """The pixels of `image` (BGR) more than `tolerance` from `colour` (RGB) in
    any channel."""
    return (np.abs(image - colour[::-1]) > tolerance).any(axis=2)


def _longest_run(flags: NDArray[np.bool_]) -> int:
    """The longest run of `True` in a 1-D array."""
    longest = run = 0
    for flag in flags.tolist():
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


def _text_kind(ink: NDArray[np.int16]) -> ChatKind:
    """
    The kind of a row on the backdrop, from its text pixels `ink` (`N x 3`,
    BGR): the kind of `TEXT_COLOURS` every pixel is a colour of, `unknown` when
    some pixel is none of them, or they are of more than one kind.
    """
    brightest = ink.max(axis=1, keepdims=True).astype(np.float64)
    explained = (brightest >= INK_MIN)[:, 0]
    kinds: set[ChatKind] = set()
    of_some_colour = np.zeros(len(ink), dtype=bool)
    for colour, kind in TEXT_COLOURS.items():
        bgr = np.array(colour[::-1], np.float64)
        dimmed = bgr * brightest / bgr.max()
        this = explained & (np.abs(ink - dimmed) <= COLOUR_TOLERANCE).all(axis=1)
        if this.any():
            kinds.add(kind)
        of_some_colour |= this
    if not of_some_colour.all() or len(kinds) != 1:
        return ChatKind.UNKNOWN
    return kinds.pop()


class _Cursor:
    """
    Where the mouse cursor is drawn over the log's rows. It is looked for only
    when a row asks, and once per read.
    """

    def __init__(
        self,
        pixels: NDArray[np.uint8],
        cursors: list[NDArray[np.uint8]],
        x: int,
        top: int,
        bottom: int,
        tolerance: float,
    ) -> None:
        """`top` is the log's top, and `bottom` where its rows end
        (`LOG_BOTTOM`), whose row the last row's cell reaches."""
        self._pixels = pixels
        self._cursors = cursors
        self._area = (x + BAND_LEFT, top, BAND_RIGHT - BAND_LEFT, bottom + 1 - top)
        self._tolerance = tolerance
        self._mask: NDArray[np.bool_] | None = None

    def over(self, top: int, bottom: int) -> NDArray[np.bool_]:
        """Which pixels of the rows' band, from client row `top` to `bottom`
        (excluded), the cursor is drawn over."""
        mask = self._mask
        if mask is None:
            mask = cursor_mask(self._pixels, self._cursors, self._area, self._tolerance)
            self._mask = mask
        first = self._area[1]
        return mask[top - first : bottom - first]


def _new_rows(previous: Sequence[_Row] | None, rows: Sequence[_Row]) -> list[_Row]:
    """
    The rows of `rows` that `previous` doesn't explain, without the empty ones.

    The log scrolls up as lines arrive: with `k` new lines, the top rows of
    `rows` are the bottom rows of `previous`, shifted up by `k`. The smallest
    such `k` is taken, so an unchanged log has no new line.
    """
    if previous is None:
        return [row for row in rows if row.kind is not None]
    n = len(rows)
    for k in range(n + 1):
        kept = n - k
        if kept <= len(previous) and list(rows[:kept]) == list(
            previous[len(previous) - kept :]
        ):
            return [row for row in rows[kept:] if row.kind is not None]
    raise AssertionError("k == n always explains the rows")
