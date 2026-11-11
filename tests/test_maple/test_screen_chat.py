"""
The chat reader on synthetic frames: made-up sprites of the client's sizes and
origins, rows of the log painted in the frame set's band and text colours, and
made-up glyphs. No client pixels.
"""

from dataclasses import dataclass

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.sprites import Sprite
from maple.screen.chat import (
    BAND_LEFT,
    BAND_RIGHT,
    FADE,
    LOG_BOTTOM,
    LOG_HIDDEN,
    LOG_SHOWN,
    MEGAPHONE_BANDS,
    ROW_HEIGHT,
    SCROLL_UP,
    SCROLL_X,
    TARGET_SELECT,
    ChatKind,
    ChatLine,
    ChatReader,
    reads_as,
)
from maple.screen.cursor import CURSOR_PATHS
from maple.screen.font import CHAT_GENERAL, UNREAD, GlyphSet
from maple.screen.locator import UI_NOT_FOUND, FrameCheck
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

RNG = np.random.default_rng(315)

type RGB = tuple[int, int, int]

YELLOW_BAND = MEGAPHONE_BANDS["yellow"].dark
PINK_BAND = MEGAPHONE_BANDS["pink"].dark
TEAL_BAND = MEGAPHONE_BANDS["teal"].dark
BLUE_BAND = MEGAPHONE_BANDS["light blue"].dark
BACKDROP: RGB = (20, 20, 10)
BRIGHT_BACKDROP: RGB = (119, 119, 124)
"""The backdrop over a bright map: a row's end on henesyscrowd_044 (v3)."""
WHITE: RGB = (255, 255, 255)
YELLOW: RGB = (255, 255, 0)
NOTICE_BLUE: RGB = (96, 206, 255)
GREEN: RGB = (0, 255, 0)
DARK_RED: RGB = (170, 0, 90)
"""A band not captured yet, brighter than the backdrop and off every band."""
WINDOW: RGB = (240, 240, 240)


def sprite(path: str, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> Sprite:
    # Channels kept off the backdrop's, band and text colours, so a sprite
    # never matches a painted row by accident.
    rgba = RNG.integers(30, 220, (h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    return Sprite(path, rgba, origin)


# The client's sizes and origins.
SPRITES = {
    TARGET_SELECT: sprite(TARGET_SELECT, 80, 18, (-8, -11)),
    LOG_SHOWN: sprite(LOG_SHOWN, 12, 12, (-539, -14)),
    LOG_HIDDEN: sprite(LOG_HIDDEN, 12, 12, (-539, -14)),
    SCROLL_UP: sprite(SCROLL_UP, 15, 13),
    GAUGE_LABEL: sprite(GAUGE_LABEL, 20, 8),
    **{path: sprite(path, 20, 26) for path in CURSOR_PATHS},
}
CURSOR = SPRITES[CURSOR_PATHS[0]]


def glyph(columns: list[int]) -> np.ndarray:
    """A 14-row glyph, each column inked over the rows `3..3+n`."""
    mask = np.zeros((CHAT_GENERAL.rows or 14, len(columns)), bool)
    for x, n in enumerate(columns):
        mask[3 : 3 + n, x] = True
    return mask


def marks(columns: list[list[int]]) -> np.ndarray:
    """A 14-row glyph, each column inked on the rows it lists."""
    mask = np.zeros((CHAT_GENERAL.rows or 14, len(columns)), bool)
    for x, rows in enumerate(columns):
        mask[rows, x] = True
    return mask


GLYPHS = {
    "H": glyph([9, 2, 2, 9]),
    "i": glyph([1, 0, 9]),
    "!": glyph([7]),
    ":": marks([[5, 6, 10, 11]]),
    "1": marks([[4], list(range(3, 12))]),
    "[": marks([list(range(2, 13)), [2, 12]]),
    "]": marks([[2, 12], list(range(2, 13))]),
}
UNHARVESTED = glyph([5, 5, 1, 5, 5])
"""A glyph the set doesn't have, drawn where a row's text says `UNREAD`."""


def sprites() -> ReaderSprites:
    return ReaderSprites(
        "build",
        dict(SPRITES),
        glyph_sets={CHAT_GENERAL.name: GlyphSet(CHAT_GENERAL, GLYPHS)},
    )


def reader(ign: str | None = None) -> ChatReader:
    s = sprites()
    return ChatReader(s, FrameCheck(s), ign=ign)


def paste(pixels: np.ndarray, s: Sprite, x: int, y: int) -> None:
    """Draw `s` with its origin on `(x, y)`."""
    h, w = s.rgba.shape[:2]
    left, top = x - s.origin[0], y - s.origin[1]
    pixels[top : top + h, left : left + w] = s.rgba[:, :, 2::-1]


@dataclass
class Row:
    """One row of the log: its band (or the backdrop), and its text, where
    `UNREAD` draws a glyph the set lacks."""

    background: RGB = BACKDROP
    text: str = ""
    colour: RGB = WHITE
    right_end: RGB | None = None
    """The band's colour at its right end, when the map behind it makes it
    differ from its left end's."""


POINT = (40, 200)
"""Where the chat is drawn from, in the synthetic frames."""


def screen(w: int = 700, h: int = 260) -> np.ndarray:
    pixels = np.full((h, w, 3), (8, 8, 8), dtype=np.uint8)
    paste(pixels, SPRITES[GAUGE_LABEL], 10, h - 12)
    return pixels


def draw_chat(
    pixels: np.ndarray,
    rows: list[Row],
    point: tuple[int, int] = POINT,
    hidden: bool = False,
    fade: bool = True,
) -> None:
    """Draw the chat, and its log's `rows`, faded at the log's bottom as the
    client draws it, unless not to `fade`."""
    x, y = point
    paste(pixels, SPRITES[TARGET_SELECT], x, y)
    paste(pixels, SPRITES[LOG_HIDDEN if hidden else LOG_SHOWN], x, y)
    if hidden:
        return
    bottom = y + LOG_BOTTOM
    top = bottom - ROW_HEIGHT * len(rows)
    paste(pixels, SPRITES[SCROLL_UP], x + SCROLL_X, top)
    for i, row in enumerate(rows):
        row_top = top + ROW_HEIGHT * i
        left, right = x + BAND_LEFT, x + BAND_RIGHT
        ends = np.array([row.background, row.right_end or row.background], float)
        across = np.linspace(0.0, 1.0, right - left)[:, np.newaxis]
        band = (ends[0] + across * (ends[1] - ends[0])).round().astype(np.uint8)
        pixels[row_top : row_top + ROW_HEIGHT, left:right] = band[:, ::-1]
        masks = [{**GLYPHS, UNREAD: UNHARVESTED}.get(c) for c in row.text]
        cx = x + BAND_LEFT + 2
        for mask in masks:
            if mask is None:  # a space: a gap of 3 columns or more
                cx += 3
                continue
            h, w = mask.shape
            # Glyph cells start 3 rows down, and run 2 rows into the next row,
            # where no glyph here inks.
            cell = pixels[row_top + 3 : row_top + 3 + h, cx : cx + w]
            cell[mask[: cell.shape[0]]] = row.colour[::-1]
            cx += w + 1
    if fade:
        first = bottom - len(FADE) + 1
        for i, level in enumerate(FADE):
            band = pixels[first + i, x + BAND_LEFT : x + BAND_RIGHT]
            band[:] = (band * (level / 255)).round().astype(np.uint8)


def frame(pixels: np.ndarray, ok: bool = True) -> Frame:
    return Frame(
        pixels, (pixels.shape[1], pixels.shape[0]), 1.0, True, ok, "" if ok else "x"
    )


def chat_frame(rows: list[Row], **kwargs: object) -> Frame:
    pixels = screen()
    draw_chat(pixels, rows, **kwargs)  # pyright: ignore[reportArgumentType]
    return frame(pixels)


def kinds(rows: list[Row]) -> list[ChatKind]:
    reading = reader().read(chat_frame(rows))
    assert reading.status is Status.READ, reading.detail
    assert reading.value is not None
    return [line.kind for line in reading.value]


# --- kinds ----------------------------------------------------------------


@pytest.mark.parametrize("name", MEGAPHONE_BANDS)
def test_a_megaphone_band_is_a_megaphone(name: str) -> None:
    assert kinds([Row(MEGAPHONE_BANDS[name].dark, "Hi", WHITE)]) == [
        ChatKind.MEGAPHONE
    ]


@pytest.mark.parametrize(
    "band",
    [
        (132, 67, 49),  # red over Ellinia: j_1280x720_pagedown_3 (v2)
        (166, 80, 72),  # red, where Henesys's grass shows behind: henesyscrowd_004
        (187, 105, 106),  # red over Henesys: henesyscrowd_000 (v3)
        (175, 195, 214),  # light blue over Henesys: henesyscrowd_030 (v3)
        (238, 189, 17),  # yellow over Ellinia's brightest: ellinia_042 (v3)
        (229, 178, 202),  # pink, the same: ellinia_036 (v3)
    ],
)
def test_a_band_over_a_map_that_shows_through_it_is_still_a_megaphone(
    band: RGB,
) -> None:
    """A band is translucent: the colours its ends read on the frame set, by
    up to 50 levels apart for the red band."""
    assert kinds([Row(band, "Hi", WHITE)]) == [ChatKind.MEGAPHONE]


def test_a_band_whose_ends_differ_over_the_map_behind_it_is_one_band() -> None:
    """henesys_1280x720_08 (v3): a red band's ends, over two parts of the map."""
    row = Row((157, 84, 66), "Hi", WHITE, right_end=(178, 101, 102))
    assert kinds([row]) == [ChatKind.MEGAPHONE]


def test_a_band_drawn_a_little_off_its_colour_is_still_that_band() -> None:
    r, g, b = BLUE_BAND
    assert kinds([Row((r + 3, g + 13, b), "Hi", WHITE)]) == [ChatKind.MEGAPHONE]


@pytest.mark.parametrize(
    ("colour", "kind"),
    [(WHITE, ChatKind.GENERAL), (YELLOW, ChatKind.SYSTEM), (NOTICE_BLUE, ChatKind.SYSTEM)],
    ids=["general", "system", "event notice"],
)
def test_a_line_over_a_bright_map_has_its_kind(colour: RGB, kind: ChatKind) -> None:
    """The backdrop is black at half opacity, so over Henesys it reads up to
    127, the ends of a row included, and its rows are no band."""
    left, right = BRIGHT_BACKDROP, BACKDROP
    assert kinds([Row(left, "Hi", colour, right_end=right)]) == [kind]


def test_a_general_line_over_a_bright_map_is_read() -> None:
    line = read_one(Row(BRIGHT_BACKDROP, "Hi : H!"))

    assert (line.kind, line.speaker, line.message) == (ChatKind.GENERAL, "Hi", "H!")


def test_an_events_notice_is_a_system_line() -> None:
    assert kinds([Row(text="Hi", colour=NOTICE_BLUE)]) == [ChatKind.SYSTEM]


def test_text_of_two_kinds_is_unknown() -> None:
    pixels = screen()
    draw_chat(pixels, [Row(text="Hi Hi")])
    top = POINT[1] + LOG_BOTTOM - ROW_HEIGHT
    text = pixels[top : top + ROW_HEIGHT, POINT[0] + BAND_LEFT + 12 :]
    text[(text == 255).all(axis=2)] = YELLOW[::-1]
    reading = reader().read(frame(pixels))

    assert reading.value is not None
    assert [line.kind for line in reading.value] == [ChatKind.UNKNOWN]


def test_the_newest_line_is_read_where_the_log_fades_out() -> None:
    """The log's last rows of pixels fade, and the bottom row's baseline and
    descenders are drawn in them: its text is still read."""
    faded = chat_frame([Row(text="H"), Row(text="Hi : H!")])
    unfaded = screen()
    draw_chat(unfaded, [Row(text="H"), Row(text="Hi : H!")], fade=False)

    assert not np.array_equal(faded.pixels, unfaded)
    reading = reader().read(faded)
    assert reading.value is not None
    assert [(line.text, line.speaker) for line in reading.value] == [
        ("H", None),
        ("Hi : H!", "Hi"),
    ]


def cursor_over(rows: list[Row], column: int, row: int = 0) -> Frame:
    """The log's `rows`, with the cursor drawn over the given row, from
    `column` of its band. The cursor is taller than a row, so it covers the
    next row too."""
    pixels = screen()
    draw_chat(pixels, rows)
    top = POINT[1] + LOG_BOTTOM - ROW_HEIGHT * (len(rows) - row)
    paste(pixels, CURSOR, POINT[0] + BAND_LEFT + column, top + 4)
    return frame(pixels)


@pytest.mark.parametrize(
    ("colour", "kind"),
    [(WHITE, ChatKind.GENERAL), (YELLOW, ChatKind.SYSTEM)],
    ids=["general", "system"],
)
def test_the_cursor_over_a_line_is_none_of_its_text(
    colour: RGB, kind: ChatKind
) -> None:
    reading = reader().read(cursor_over([Row(text="Hi Hi!", colour=colour), Row(), Row()], 12))

    assert reading.status is Status.READ
    assert reading.value is not None
    assert [line.kind for line in reading.value] == [kind]


def test_what_the_cursor_hides_reads_unread() -> None:
    """Never a line with its letters left out: the columns the cursor covers,
    here the whole of the message, read as one letter that has no glyph."""
    reading = reader().read(cursor_over([Row(text="Hi : Hi!"), Row(), Row()], 18))

    assert reading.value is not None
    [line] = reading.value
    assert (line.text, line.speaker) == (f"Hi : {UNREAD}", "Hi")


def test_the_cursor_over_an_empty_row_is_no_line() -> None:
    reading = reader().read(cursor_over([Row(text="Hi"), Row(), Row(), Row()], 40, row=1))

    assert reading.value is not None
    assert [line.text for line in reading.value] == ["Hi"]


def test_white_text_with_no_band_is_general_and_is_read() -> None:
    reading = reader().read(chat_frame([Row(text="Hi Hi!")]))
    assert reading.value is not None
    [line] = reading.value
    assert line.kind is ChatKind.GENERAL
    assert line.text == "Hi Hi!"


def test_yellow_text_with_no_band_is_system_and_has_no_text() -> None:
    reading = reader().read(chat_frame([Row(text="Hi", colour=YELLOW)]))
    assert reading.value is not None
    assert [(line.kind, line.text) for line in reading.value] == [
        (ChatKind.SYSTEM, None)
    ]


@pytest.mark.parametrize(
    "row",
    [
        Row(text="Hi", colour=GREEN),  # a colour not captured yet: whisper?
        Row(DARK_RED, "Hi", WHITE),  # a band not captured yet
    ],
    ids=["text colour", "band"],
)
def test_colours_not_in_the_frame_set_are_unknown(row: Row) -> None:
    assert kinds([row]) == [ChatKind.UNKNOWN]


def test_no_kind_is_ever_guessed_as_party_buddy_whisper_or_gm() -> None:
    """Their colours aren't in the frame set, so nothing reads as them yet."""
    rows = [
        Row(text="Hi"),
        Row(text="Hi", colour=GREEN),
        Row(DARK_RED, "Hi"),
        Row(PINK_BAND, "Hi", DARK_RED),
    ]
    assert not {ChatKind.PARTY, ChatKind.BUDDY, ChatKind.WHISPER, ChatKind.GM} & set(
        kinds(rows)
    )


def test_empty_rows_are_not_lines() -> None:
    assert kinds([Row(), Row(), Row(text="Hi"), Row(TEAL_BAND, "i")]) == [
        ChatKind.GENERAL,
        ChatKind.MEGAPHONE,
    ]


def read_one(row: Row, ign: str | None = None) -> ChatLine:
    reading = reader(ign).read(chat_frame([row]))
    assert reading.value is not None, reading.detail
    [line] = reading.value
    return line


def test_a_character_not_harvested_reads_as_unread_in_its_place() -> None:
    """The line keeps its kind and the rest of its text, rather than reading
    `None` or a string with the character missing."""
    line = read_one(Row(text=f"H{UNREAD}i H{UNREAD}"))

    assert line.kind is ChatKind.GENERAL
    assert line.text == f"H{UNREAD}i H{UNREAD}"


# --- speaker and message ----------------------------------------------------


def test_a_general_line_is_split_into_its_speaker_and_message() -> None:
    line = read_one(Row(text="Hi : Hi H! i"))

    assert (line.text, line.speaker, line.message) == ("Hi : Hi H! i", "Hi", "Hi H! i")
    assert not line.outgoing


def test_the_time_before_a_general_line_is_neither_speaker_nor_message() -> None:
    line = read_one(Row(text="[11:1] HiH : i"))

    assert (line.speaker, line.message) == ("HiH", "i")


def test_a_message_that_holds_the_separator_is_split_at_the_first() -> None:
    line = read_one(Row(text="Hi : H : i"))

    assert (line.speaker, line.message) == ("Hi", "H : i")


@pytest.mark.parametrize(
    "text",
    ["Hi H!", f"H{UNREAD} H", "Hi :", "H! : i", ": i"],
    ids=["no separator", "wrapped row", "no message", "not a name", "no name"],
)
def test_a_general_row_that_doesnt_fit_the_format_has_no_speaker(text: str) -> None:
    line = read_one(Row(text=text))

    assert (line.kind, line.text) == (ChatKind.GENERAL, text)
    assert (line.speaker, line.message, line.outgoing) == (None, None, False)


def test_an_unread_letter_in_a_name_is_kept_in_the_speaker() -> None:
    line = read_one(Row(text=f"H{UNREAD}i : i"))

    assert (line.speaker, line.message) == (f"H{UNREAD}i", "i")


@pytest.mark.parametrize(
    ("ign", "outgoing"),
    [("Hi", True), ("hI", True), ("Hl", False), ("Hii", False), ("H", False)],
)
def test_a_line_is_outgoing_when_its_speaker_is_the_character(
    ign: str, outgoing: bool
) -> None:
    assert read_one(Row(text="Hi : i"), ign=ign).outgoing is outgoing


def test_a_speaker_read_in_part_is_the_character_when_the_rest_reads_as_it() -> None:
    line = read_one(Row(text=f"H{UNREAD} : i"), ign="Hx")

    assert line.outgoing


def test_no_line_is_outgoing_without_the_character_s_name() -> None:
    assert not read_one(Row(text="Hi : i")).outgoing


@pytest.mark.parametrize(
    "row",
    [Row(TEAL_BAND, "Hi : i"), Row(text="Hi : i", colour=YELLOW)],
    ids=["megaphone", "system"],
)
def test_other_kinds_have_no_speaker(row: Row) -> None:
    line = read_one(row, ign="Hi")

    assert (line.speaker, line.message, line.outgoing) == (None, None, False)


@pytest.mark.parametrize(
    ("read", "written", "same"),
    [
        ("Hi", "Hi", True),
        ("IoI", "lol", True),
        ("IoI", "IoI", True),
        ("lol", "IoI", False),
        (f"H{UNREAD}", "Hx", True),
        ("Hi", "Hi!", False),
        ("Hi", "hi", False),
    ],
)
def test_reads_as_allows_unread_and_alike_letters(
    read: str, written: str, same: bool
) -> None:
    assert reads_as(read, written) is same


def test_reads_as_may_ignore_case() -> None:
    assert reads_as("HI", "hl", ignore_case=True)
    assert not reads_as("HI", "hx", ignore_case=True)


def test_a_line_carries_its_row_image_and_top() -> None:
    reading = reader().read(chat_frame([Row(YELLOW_BAND, "Hi"), Row(text="i")]))
    assert reading.value is not None
    first, second = reading.value
    assert first.image.shape == (ROW_HEIGHT, BAND_RIGHT - BAND_LEFT, 3)
    assert second.top - first.top == ROW_HEIGHT
    assert second.top + ROW_HEIGHT == POINT[1] + LOG_BOTTOM


def test_the_log_is_as_tall_as_its_arrow_says() -> None:
    """4 rows in frame set v1, 6 in v2's taller log: whatever fits under the
    arrow is read."""
    six = [Row(text="i")] * 5 + [Row(PINK_BAND, "H")]
    assert len(kinds(six)) == 6


# --- new lines ------------------------------------------------------------


def test_each_line_is_reported_once() -> None:
    r = reader()
    log = [Row(YELLOW_BAND, "Hi"), Row(text="H"), Row(text="i"), Row(PINK_BAND, "H")]
    first = r.read(chat_frame(log))
    again = r.read(chat_frame(log))
    assert first.value is not None
    assert len(first.value) == 4
    assert again.status is Status.READ
    assert again.value == []


def test_lines_that_scroll_the_log_up_are_the_new_ones() -> None:
    r = reader()
    log = [Row(YELLOW_BAND, "Hi"), Row(text="H"), Row(text="i"), Row(PINK_BAND, "H")]
    r.read(chat_frame(log))
    arrived = [Row(text="Hi!"), Row(TEAL_BAND, "i")]
    reading = r.read(chat_frame(log[2:] + arrived))
    assert reading.value is not None
    assert [(line.kind, line.text) for line in reading.value] == [
        (ChatKind.GENERAL, "Hi!"),
        (ChatKind.MEGAPHONE, None),
    ]


def test_a_log_with_nothing_in_common_is_all_new() -> None:
    r = reader()
    r.read(chat_frame([Row(text="H")] * 4))
    reading = r.read(chat_frame([Row(text="i")] * 4))
    assert reading.value is not None
    assert len(reading.value) == 4


def test_a_covered_read_changes_nothing_the_next_read_compares_with() -> None:
    r = reader()
    log = [Row(text="H"), Row(text="i"), Row(text="Hi"), Row(text="Hi!")]
    r.read(chat_frame(log))
    pixels = screen()
    draw_chat(pixels, log)
    pixels[POINT[1] - 30 : POINT[1] - 10, POINT[0] + 100 : POINT[0] + 300] = WINDOW
    assert r.read(frame(pixels)).status is Status.COVERED
    assert r.read(chat_frame(log)).value == []


def test_forget_makes_every_line_new_again() -> None:
    r = reader()
    log = [Row(text="H"), Row(text="i")]
    r.read(chat_frame(log))
    r.forget()
    reading = r.read(chat_frame(log))
    assert reading.value is not None
    assert len(reading.value) == 2


def test_the_chat_is_found_again_after_the_client_is_resized() -> None:
    r = reader()
    log = [Row(text="H"), Row(text="i")]
    r.read(chat_frame(log))
    pixels = screen(w=680, h=250)
    draw_chat(pixels, log, point=(30, 190))
    reading = r.read(frame(pixels))
    assert reading.status is Status.READ
    assert reading.value == []


# --- statuses -------------------------------------------------------------


def test_absent_when_no_chat_is_drawn() -> None:
    reading = reader().read(frame(screen()))
    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_absent_while_the_log_is_hidden() -> None:
    reading = reader().read(chat_frame([], hidden=True))
    assert reading.status is Status.ABSENT
    assert reading.value is None
    assert "hidden" in reading.detail


def test_covered_when_something_is_over_the_target_button() -> None:
    pixels = screen()
    draw_chat(pixels, [Row(text="H")])
    pixels[POINT[1] + 12 : POINT[1] + 20, POINT[0] + 20 : POINT[0] + 30] = WINDOW
    reading = reader().read(frame(pixels))
    assert reading.status is Status.COVERED
    assert reading.value is None


def test_covered_when_something_is_over_the_logs_toggle() -> None:
    pixels = screen()
    draw_chat(pixels, [Row(text="H")])
    pixels[POINT[1] + 15 : POINT[1] + 20, POINT[0] + 540 : POINT[0] + 545] = WINDOW
    assert reader().read(frame(pixels)).status is Status.COVERED


def test_covered_when_something_is_over_the_logs_arrow() -> None:
    rows = [Row(text="H"), Row(text="i")]
    pixels = screen()
    draw_chat(pixels, rows)
    top = POINT[1] + LOG_BOTTOM - ROW_HEIGHT * len(rows)
    pixels[top : top + 6, POINT[0] + SCROLL_X : POINT[0] + SCROLL_X + 6] = WINDOW
    assert reader().read(frame(pixels)).status is Status.COVERED


@pytest.mark.parametrize(
    "columns",
    [(BAND_LEFT - 4, BAND_LEFT + 40), (300, 420), (BAND_RIGHT - 60, BAND_RIGHT + 2)],
    ids=["left end", "middle", "right end"],
)
@pytest.mark.parametrize("band", [BACKDROP, PINK_BAND], ids=["backdrop", "band"])
def test_covered_when_a_window_is_over_a_row(
    columns: tuple[int, int], band: RGB
) -> None:
    rows = [Row(band, "Hi"), Row(band, "i"), Row(band, "H")]
    pixels = screen()
    draw_chat(pixels, rows)
    top = POINT[1] + LOG_BOTTOM - ROW_HEIGHT * 2
    left, right = columns
    pixels[top : top + ROW_HEIGHT, POINT[0] + left : POINT[0] + right] = WINDOW
    reading = reader().read(frame(pixels))
    assert reading.status is Status.COVERED
    assert reading.value is None


def test_unsure_on_a_frame_that_isnt_ok() -> None:
    pixels = screen()
    draw_chat(pixels, [Row(text="H")])
    reading = reader().read(frame(pixels, ok=False))
    assert reading.status is Status.UNSURE
    assert reading.value is None


def test_unsure_when_the_ui_isnt_drawn_at_1_to_1() -> None:
    pixels = np.full((260, 700, 3), 8, np.uint8)
    draw_chat(pixels, [Row(text="H")])
    reading = reader().read(frame(pixels))
    assert reading.status is Status.UNSURE
    assert reading.detail == UI_NOT_FOUND


# --- shown, and the chat's region -----------------------------------------


def test_shown_says_whether_the_log_is_shown() -> None:
    r = reader()
    assert r.shown(chat_frame([Row(text="H")])).value is True
    assert r.shown(chat_frame([], hidden=True)).value is False
    assert r.shown(frame(screen())).value is False


def test_shown_is_covered_when_neither_toggle_is_seen() -> None:
    pixels = screen()
    draw_chat(pixels, [Row(text="H")])
    pixels[POINT[1] + 15 : POINT[1] + 20, POINT[0] + 540 : POINT[0] + 545] = WINDOW
    reading = reader().shown(frame(pixels))
    assert reading.status is Status.COVERED
    assert reading.value is None


def test_the_region_runs_from_the_logs_top_to_the_bars_bottom() -> None:
    rows = [Row(text="H")] * 4
    region = reader().region(chat_frame(rows))
    assert region is not None
    assert region.top == POINT[1] + LOG_BOTTOM - ROW_HEIGHT * 4
    target = SPRITES[TARGET_SELECT]
    assert region.bottom == POINT[1] - target.origin[1] + target.rgba.shape[0]
    hidden = reader().region(chat_frame([], hidden=True))
    assert hidden is not None
    assert hidden.top == POINT[1] + LOG_BOTTOM


def test_no_region_when_the_chat_isnt_found() -> None:
    assert reader().region(frame(screen())) is None
