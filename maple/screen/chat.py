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

- a band of one of `MEGAPHONE_BANDS` is a megaphone;
- no band (the log's dark backdrop over the game) with all its text white is
  general, and all yellow is system (`TEXT_COLOURS`);
- a row with no band and no text is empty, and isn't a line;
- anything else is `unknown`: party, buddy, whisper and GM lines haven't been
  captured (frame set `v3` has none), so their colours aren't known, and they
  read `unknown` until frames of them are in the set (#456). So does a
  megaphone band not seen yet, and a general or system line over a map bright
  enough that the backdrop's ends read above `BACKDROP_MAX` (Henesys, in `v3`).

A line that wraps is one row per screen row, each with the kind of its colours.

**Text** is read for general lines, with the white glyphs harvested from the
frames (`font.CHAT_GENERAL`, #313, #456), in each row's 14-row glyph cell, 3
rows below its top. A letter with no glyph reads `UNREAD` (U+FFFD) in its place
(`GlyphSet.read_marked`), so a partly read line keeps its kind and the rest of
its text. Frame set `v3` holds 52 of the 95 printable characters in white, the
space among them (`toolkit/glyph_sources/v3.json`); the others read `UNREAD`
until frames of them are harvested. Arial draws `I` and `l` alike, so both read
`I` (`ALIKE`).
System, party, buddy, whisper and GM text waits for those colours' glyphs.

**Speaker and message** are split from a general line's text by its format,
`Name : message`, read on frame sets `v1` (f001-f005) and `v3`, where the client
puts the time before it: `[16:22] Name : message`. A name is letters and digits
(or `UNREAD`). A row that doesn't fit, the second row of a wrapped line among
them, has neither. A line is `outgoing` when its speaker reads as the
character's own name (`reads_as`, ignoring case); the outgoing whisper's format
waits for a frame of one.

**Reads as.** Whether a text read may be a given one, a name or a message, is
`reads_as`, the one place that says it: as long, and equal letter by letter,
where an `UNREAD` letter may be any letter and an `ALIKE` letter any of those
drawn like it. A text with too few letters read (`MIN_READ`) reads as nothing:
another player whose name reads mostly `UNREAD` is not the character.

**Wrapped lines.** A general row that doesn't fit the format, directly below a
general row read in the same `read`, `continues` the line above: its text is
the rest of that line's message. The reader keeps it a row of its own; the
conversation joins it to the line above (`maple.chat_replies.conversation`).
A row whose line above scrolled away before it was read can't be told from a
line that doesn't fit, and doesn't continue anything.

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
    canvases=(TARGET_SELECT, SCROLL_UP, LOG_SHOWN, LOG_HIDDEN),
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

MEGAPHONE_BANDS: dict[RGB, str] = {
    (223, 174, 1): "yellow: f001 row 1 (v1); (224, 178, 1) in j_1366x768_pageup_1 (v2)",
    (206, 155, 178): "pink: f024 rows 1-4 (v1); (209, 161, 179) in j_* (v2)",
    (82, 208, 191): "teal: f011 rows 1-4 (v1)",
    (144, 164, 179): "light blue: f001 row 4 (v1)",
}
"""Each megaphone band's colour, in RGB, and the frames it was read from. The
band is drawn a little translucent, so the same band differs by a few levels
between frames; `BAND_TOLERANCE` covers that."""
BAND_TOLERANCE = 24
"""How far, per channel, a row's end may be from a band's colour and still be
that band. Over the game, the same band drifted by up to 13 across the frame set
(light blue, f007 row 1); two bands differ by 62 or more."""
BACKDROP_MAX = 80
"""A row end with no channel above this is the log's dark backdrop, not a band:
the backdrop over the game read at most 63 at a row's ends in the frame set. A
darker band than this would be taken for the backdrop."""
TEXT_MIN = 128
"""On the backdrop, a pixel with a channel above this is text. The backdrop is
translucent, and the game behind it shows through brighter than at its ends."""
INK_MIN = 200
TEXT_COLOURS: dict[str, RGB] = {
    "white": (255, 255, 255),  # general lines: f001 rows 2-3 (v1)
    "yellow": (255, 255, 0),  # system lines: f065 rows 3-4 (v1)
}
"""The text colours of the rows with no band. On the backdrop, any pixel with a
channel above `TEXT_MIN` is text. It is white when every channel is at least
`INK_MIN`, and yellow when red and green are and blue is at most
`YELLOW_BLUE_MAX`: the system lines' edges were drawn down to (243, 243, 0)."""
YELLOW_BLUE_MAX = 60
_SIGNATURE_DIFFERENCE = 48
"""On a band, a pixel more than this from the band's colour, in any channel,
is text, for the row's signature."""


ALIKE: dict[str, str] = {"I": "Il"}
"""Letters the chat's font, Arial at 14 px, draws alike: the one a line reads ->
every letter it may be (`toolkit.harvest_glyphs.alike`; a `frames` test checks
the harvested set says the same)."""

MIN_READ = 2
"""The fewest letters (spaces aside) a text must have read for `reads_as` to
match it with anything, and it must have read at least half of them too. A
shorter text must have read all of them. 43 printable characters have no glyph
yet (`font.CHAT_GENERAL`), so a 4-letter name read `UNREAD` throughout would
otherwise be anyone of 4 letters, the character among them (#484)."""

_GENERAL_FORMAT = re.compile(
    rf"(?:\[[^\]]*\] )?(?P<speaker>[A-Za-z0-9{UNREAD}]+) : (?P<message>.+)"
)
"""A general line: the time the client may put first, the speaker, then the
message (module docstring)."""


def reads_as(read: str, written: str, *, ignore_case: bool = False) -> bool:
    """
    Whether chat text read as `read` may be `written`: as long, and equal letter
    by letter, where `UNREAD` may be any letter and a letter of `ALIKE` any of
    those drawn like it. `read` must have read enough of its letters
    (`MIN_READ`): one that hasn't is never anything.
    """
    if len(read) != len(written) or not _read_enough(read):
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


def _read_enough(read: str) -> bool:
    """Whether `read` has read enough of its letters to be matched (`MIN_READ`)."""
    letters = [c for c in read if not c.isspace()]
    known = sum(c != UNREAD for c in letters)
    return (
        known > 0 and known >= min(MIN_READ, len(letters)) and 2 * known >= len(letters)
    )


class ChatKind(enum.Enum):
    GENERAL = "general"
    PARTY = "party"
    BUDDY = "buddy"
    WHISPER = "whisper"
    GM = "gm"
    MEGAPHONE = "megaphone"
    SYSTEM = "system"
    UNKNOWN = "unknown"


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
        character's name (`reads_as`, ignoring case, so it must have read
        enough of its letters).
    :ivar continues: The row is the rest of the line above, which wrapped: a
        general row that doesn't fit the format, directly below a general row of
        the same `read`. Its words are in `text` only.
    """

    kind: ChatKind
    image: NDArray[np.uint8]
    text: str | None
    top: int
    speaker: str | None = None
    message: str | None = None
    outgoing: bool = False
    continues: bool = False


@dataclass(frozen=True, slots=True)
class _Row:
    kind: ChatKind | None
    """`None` for an empty row."""
    signature: bytes
    image: NDArray[np.uint8] = field(compare=False)
    top: int = field(compare=False)


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
        rows: list[_Row] = []
        for top in self._row_tops(located, arrow):
            row = self._row(frame.pixels, located.point[0], top)
            if isinstance(row, str):
                return Reading.covered(frame.captured_at, row)
            rows.append(row)
        new = _new_rows(self._previous, rows)
        self._previous = rows
        lines: list[ChatLine] = []
        for row in new:
            above = lines[-1] if lines else None
            lines.append(self._line(frame.pixels, located.point[0], row, above))
        return Reading.read(lines, frame.captured_at)

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

    def _row(self, pixels: NDArray[np.uint8], x: int, top: int) -> _Row | str:
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
        if background == "backdrop":
            if _longest_run(pixels16[_GAP_ROW].max(axis=1) > TEXT_MIN) > COVER_RUN:
                return f"something is over the log's row at y={top}"
            ink = _backdrop_ink(own)
            if not ink.any():
                return _Row(None, b"", image, top)
            kind = _text_kind(own[ink])
        else:
            # Ends that agree on no known band are a band not seen yet, or
            # something drawn across the whole row: `unknown` either way.
            colour = (
                _median(image[:, :_END])
                if background is None
                else np.array(background, np.int16)
            )
            gap = _off(pixels16[_GAP_ROW : _GAP_ROW + 1], colour, BAND_TOLERANCE)
            if _longest_run(gap[0]) > COVER_RUN:
                return f"something is over the log's row at y={top}"
            ink = _off(own, colour, _SIGNATURE_DIFFERENCE)
            kind = ChatKind.UNKNOWN if background is None else ChatKind.MEGAPHONE
        return _Row(kind, kind.value.encode() + np.packbits(ink).tobytes(), image, top)

    def _line(
        self,
        pixels: NDArray[np.uint8],
        x: int,
        row: _Row,
        above: ChatLine | None,
    ) -> ChatLine:
        """The line of `row`; `above` is the line of the new row read before it,
        which a row that doesn't fit the format continues when it is directly
        above, and general."""
        assert row.kind is not None
        if row.kind is not ChatKind.GENERAL:
            return ChatLine(row.kind, row.image.copy(), None, row.top)
        cell_top = row.top + _CELL_TOP
        cell = pixels[
            cell_top : cell_top + (CHAT_GENERAL.rows or ROW_HEIGHT),
            x + BAND_LEFT : x + BAND_RIGHT,
        ]
        text = self._glyphs.read_marked(cell)
        split = _GENERAL_FORMAT.fullmatch(text)
        if split is None:
            continues = (
                above is not None
                and above.kind is ChatKind.GENERAL
                and above.top + ROW_HEIGHT == row.top
            )
            return ChatLine(
                row.kind, row.image.copy(), text, row.top, continues=continues
            )
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


def _background(end: NDArray[np.uint8]) -> RGB | str | None:
    """
    What a row's end shows: a megaphone band's colour, `"backdrop"` for the
    log's dark backdrop, or `None` for any other colour.
    """
    colour = _median(end)
    if int(colour.max()) <= BACKDROP_MAX:
        return "backdrop"
    for band in MEGAPHONE_BANDS:
        if (np.abs(colour - np.array(band, np.int16)) <= BAND_TOLERANCE).all():
            return band
    return None


def _backdrop_ink(image: NDArray[np.int16]) -> NDArray[np.bool_]:
    """The text pixels of a row with no band: brighter than the backdrop."""
    return image.max(axis=2) > TEXT_MIN


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
    """General when every text pixel (`N x 3`, BGR) is white, system when every
    one is yellow, `unknown` otherwise."""
    if (ink >= INK_MIN).all():
        return ChatKind.GENERAL
    yellow = (ink[:, 1:] >= INK_MIN).all(axis=1) & (ink[:, 0] <= YELLOW_BLUE_MAX)
    if yellow.all():
        return ChatKind.SYSTEM
    return ChatKind.UNKNOWN


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
