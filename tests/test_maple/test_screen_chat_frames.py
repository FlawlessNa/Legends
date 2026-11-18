"""
The chat reader on the real MSCW frame set: every expected `chat` reading, and
the text, speaker, message and `outgoing` of every line whose text is read
(general, whisper, notice).

The expected `chat` value is each visible line's kind, top to bottom. Each frame
is read by a reader that has forgotten the rows before, so every line shown is
new. The text isn't committed, because it holds other players' names: it is
labelled here by a render of Arial in the line's colour, as
`toolkit/harvest_glyphs.py` labels it, and compared with what the reader read
with the harvested glyphs (`python -m toolkit.harvest_glyphs`). The speaker and
message are split from that label too, so no name is committed either. The one
text committed is our character's own test lines (frame set `v4`), which hold
every printable character and no name. Run with `pytest -m frames`.
"""

import itertools
import re
import string
from collections.abc import Iterator

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.chat import (
    ALIKE,
    BACKDROP_MAX,
    BAND_LEFT,
    BAND_RIGHT,
    CHAT,
    ROW_HEIGHT,
    TEXT_READ,
    WRAP_INDENT,
    ChatKind,
    ChatLine,
    ChatReader,
)
from maple.screen.font import CHAT_GENERAL, UNREAD, GlyphSet, load_glyph_set
from maple.screen.locator import FrameCheck
from maple.screen.sprites import (
    FRAME_CHECK,
    Profile,
    ReaderSprites,
    load_reader_sprites,
)
from tests.frame_set import FrameSet
from toolkit import harvest_glyphs

pytestmark = [pytest.mark.frames, pytest.mark.client_files]


NOBODY = "Qx0q"
"""A made-up name, which no line of the frame set is from."""

# v4's name-tag frames carry no `chat` reading: they are #457's.
NOT_READ_YET = ("nametags_",)


@pytest.fixture(scope="module")
def sprites() -> ReaderSprites:
    return load_reader_sprites(
        [FRAME_CHECK, CHAT],
        Profile(job="Swordsman"),
        STORE,
        config=CONFIG,
    )


@pytest.fixture(scope="module")
def reader(sprites: ReaderSprites) -> ChatReader:
    return ChatReader(sprites, FrameCheck(sprites), ign=NOBODY)


def _frame(frames: FrameSet, file: str) -> Frame:
    entry = next(e for e in frames.entries if e.file == file)
    return Frame(frames.pixels(entry), entry.client_size, 0.0, True, True)


def test_every_expected_chat_reading(frames: FrameSet, reader: ChatReader) -> None:
    wrong: list[str] = []
    checked = covered = 0
    for entry in frames.entries:
        expected = entry.expect.get("chat")
        if expected is None:
            continue
        checked += 1
        covered += expected.status is Status.COVERED
        reader.forget()
        reading = reader.read(_frame(frames, entry.file))
        kinds = (
            [line.kind.value for line in reading.value]
            if reading.value is not None
            else None
        )
        if (reading.status, kinds) != (expected.status, expected.value):
            wrong.append(
                f"{entry.file}: expected {expected.status.name} {expected.value}, "
                f"got {reading.status.name} {kinds} {reading.detail}"
            )
    assert checked
    assert covered
    assert not wrong, "\n".join(wrong)


def test_a_frame_read_twice_has_no_new_line_the_second_time(
    frames: FrameSet, reader: ChatReader
) -> None:
    """The text pixels that tell a line from another are stable on the same
    pixels, whatever the line."""
    for entry in frames.entries:
        reader.forget()
        frame = _frame(frames, entry.file)
        if reader.read(frame).status is not Status.READ:
            continue
        again = reader.read(frame)
        assert again.value == [], entry.file


def _text_lines(
    frames: FrameSet, reader: ChatReader
) -> Iterator[tuple[str, ChatLine, str | None]]:
    """Every line of the frame set whose text is read: its frame, the line, and
    its label (`_labelled`)."""
    if not harvest_glyphs.ARIAL.is_file():
        pytest.skip(f"the labelling font {harvest_glyphs.ARIAL} isn't on this machine")
    labellers = _labellers()
    for entry in frames.entries:
        if entry.file.startswith(NOT_READ_YET):
            continue
        reader.forget()
        frame = _frame(frames, entry.file)
        reading = reader.read(frame)
        region = reader.region(frame)
        for line in reading.value or []:
            if line.kind not in TEXT_READ:
                continue
            assert region is not None
            yield entry.file, line, _labelled(frame, region.left, line, labellers)


CLIENT_LETTERS = "AK#"
"""The letters the client draws unlike Arial (`font.CHAT_GENERAL`)."""


def _labellers() -> list[dict[str, np.ndarray]]:
    """
    Arial's render, then the same with the client's own `A`, `K` and `#`, for
    the lines Arial alone doesn't explain. Those three were labelled by a person
    on our test lines (`toolkit/glyph_sources/v4.json`) and are taken from the
    harvested set: for them, and only them, the label is the harvest's word.
    Every whisper and notice of `v4` needs them: they name a player whose name
    starts with the client's `A`.
    """
    arial = harvest_glyphs.font_labeller(harvest_glyphs.ARIAL)
    glyphs = load_glyph_set(CHAT_GENERAL.name)
    client = dict(arial)
    for char in CLIENT_LETTERS:
        for mask in (glyphs.glyphs[char], *glyphs.forms.get(char, ())):
            rows = np.flatnonzero(mask.any(axis=1))
            cut = mask[rows[0] : rows[-1] + 1]
            if cut.shape != arial[char].shape or (cut != arial[char]).any():
                client[char] = cut
    return [arial, client]


def test_every_line_whose_text_is_read_reads_as_arial_labels_it(
    frames: FrameSet, reader: ChatReader
) -> None:
    """Text is compared with the labeller's, never committed. Every line the
    labeller explains has its glyphs harvested, so none reads `UNREAD`; one it
    doesn't explain (a letter the client draws unlike Arial, or the faded
    pixels of the newest row) must still read, as some text."""
    read: set[ChatKind] = set()
    wrong: list[str] = []
    for file, line, labelled in _text_lines(frames, reader):
        if line.text is None:
            wrong.append(f"{file} row {line.top}: a {line.kind.value} line, no text")
        elif labelled is not None and line.text.replace(" ", "") != labelled:
            wrong.append(f"{file} row {line.top}: read text not the label")
        elif labelled is not None:
            read.add(line.kind)
    assert read == set(TEXT_READ)
    assert not wrong, "\n".join(wrong)


def test_every_line_has_the_speaker_message_and_direction_its_label_has(
    frames: FrameSet, reader: ChatReader
) -> None:
    """
    The label is split by hand here, by the line's kind: the time in brackets,
    then on general the name up to the first `:`, on a whisper the recipient up
    to the first `<<` (a whisper we sent, so outgoing, whoever we are); a
    notice has neither. A row indented as a wrapped line's next rows are has
    neither either. The label has no spaces, so neither has what is compared.
    """
    split: set[ChatKind] = set()
    wrong: list[str] = []
    for file, line, labelled in _text_lines(frames, reader):
        if labelled is None:
            continue
        expected = None if _indented(line) else _label_split(line.kind, labelled)
        got = (
            None
            if line.speaker is None or line.message is None
            else (line.speaker, line.message.replace(" ", ""))
        )
        if got != expected:
            wrong.append(f"{file} row {line.top}: split not as labelled")
        elif line.outgoing != (line.kind is ChatKind.WHISPER and got is not None):
            wrong.append(f"{file} row {line.top}: outgoing {line.outgoing}")
        if expected is not None:
            split.add(line.kind)
    assert split == {ChatKind.GENERAL, ChatKind.WHISPER}
    assert not wrong, "\n".join(wrong)


def test_a_line_is_outgoing_when_the_character_is_its_speaker(
    frames: FrameSet, sprites: ReaderSprites
) -> None:
    """Each frame's speakers, taken in turn as the character's name, in another
    case: their lines, and only theirs, are outgoing."""
    checked = 0
    wrong: list[str] = []
    for file, line, _ in _text_lines(frames, ChatReader(sprites, FrameCheck(sprites))):
        if line.speaker is None or line.kind is not ChatKind.GENERAL:
            continue
        as_speaker = ChatReader(sprites, FrameCheck(sprites), ign=line.speaker.lower())
        reading = as_speaker.read(_frame(frames, file))
        assert reading.value is not None
        for other in reading.value:
            if other.kind is not ChatKind.GENERAL:
                continue
            if other.outgoing != (other.speaker == line.speaker):
                wrong.append(f"{file} row {other.top}: outgoing {other.outgoing}")
        checked += 1
    assert checked
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize(
    "file", ["henesysL_1920x1080_11.png", "henesyscrowd_1920x1080_048.png"]
)
def test_the_newest_line_reads_whole_where_the_log_fades(
    frames: FrameSet, reader: ChatReader, file: str
) -> None:
    """The newest line's baseline and descenders are drawn where the log fades
    out (#483): on these frames, its letters there still read, none `UNREAD`.
    The text isn't compared with Arial's label, which can't label the faded
    pixels, nor printed, since it holds a player's name."""
    reader.forget()
    reading = reader.read(_frame(frames, file))
    assert reading.value is not None, reading.detail
    newest = max(reading.value, key=lambda line: line.top)

    assert newest.kind is ChatKind.GENERAL
    assert newest.text is not None
    unread = newest.text.count(UNREAD)
    assert unread == 0, f"{unread} letters of the newest line read UNREAD"


def test_the_harvested_chat_glyphs_are_as_the_reader_reads_them() -> None:
    glyphs: GlyphSet = load_glyph_set(CHAT_GENERAL.name)

    assert dict(glyphs.alike) == {k: v for k, v in ALIKE.items() if k in glyphs.glyphs}
    assert UNREAD not in glyphs.glyphs
    assert set(glyphs.bearings) == set(glyphs.glyphs), "spaces need every bearing"


_TIME = re.compile(r"\[[^\]]*\]")
_SEPARATORS = {ChatKind.GENERAL: ":", ChatKind.WHISPER: "<<"}


def _label_split(kind: ChatKind, labelled: str) -> tuple[str, str] | None:
    """The speaker and message of a label (no spaces): the time in brackets the
    client may put first, the name up to the kind's separator (the first `:` on
    general, `<<` on a whisper), then the rest. A notice has none."""
    separator = _SEPARATORS.get(kind)
    if separator is None:
        return None
    rest = _TIME.sub("", labelled, count=1) if labelled.startswith("[") else labelled
    speaker, found, message = rest.partition(separator)
    if not found or not speaker.isalnum() or not message:
        return None
    return speaker, message


def _labelled(
    frame: Frame, x: int, line: ChatLine, labellers: list[dict[str, np.ndarray]]
) -> str | None:
    """The line's text as the first of `labellers` that explains every pixel
    labels it, in the line's colour, `I` for `I` and `l` alike, without spaces;
    `None` when none does. `x` is the chat's point."""
    cell_top = line.top + harvest_glyphs.CELL_OFFSET
    cell = frame.pixels[
        cell_top : cell_top + (CHAT_GENERAL.rows or 0), x + BAND_LEFT : x + BAND_RIGHT
    ]
    ink = CHAT_GENERAL.in_colour(TEXT_READ[line.kind]).ink(cell)
    for labeller in labellers:
        harvest = harvest_glyphs.harvest_lines([("line", ink)], labeller)
        if not harvest.problems and harvest.labels:
            return harvest.labels[0][1]
    return None


def _indented(line: ChatLine) -> bool:
    """Whether the row's text starts as far in as a wrapped line's next rows,
    from its pixels: its first column with a channel above the backdrop's."""
    own = line.image[harvest_glyphs.CELL_OFFSET :].max(axis=2) > BACKDROP_MAX
    columns = np.flatnonzero(own.any(axis=0))
    return bool(len(columns)) and int(columns[0]) >= WRAP_INDENT


def _read(frames: FrameSet, reader: ChatReader, file: str) -> list[ChatLine]:
    reader.forget()
    reading = reader.read(_frame(frames, file))
    assert reading.value is not None, f"{file}: {reading.detail}"
    return reading.value


def _chat_frames(first: int, last: int) -> list[str]:
    return [f"chat_1920x1080_{n:03d}.png" for n in range(first, last + 1)]


# Wrapped lines.


def test_an_indented_row_continues_the_line_directly_above_and_no_other_does(
    frames: FrameSet, reader: ChatReader
) -> None:
    """A wrapped line's next rows are drawn indented (`WRAP_INDENT`); a row
    that starts where a line starts never continues the one above, whatever
    its text (#484's caveat)."""
    continued = 0
    wrong: list[str] = []
    for file, line, _ in _text_lines(frames, reader):
        if line.continues and not _indented(line):
            wrong.append(f"{file} row {line.top}: continues, not indented")
        continued += line.continues
    for entry in frames.entries:
        if entry.file.startswith(NOT_READ_YET):
            continue
        reader.forget()
        lines = reader.read(_frame(frames, entry.file)).value or []
        for above, line in itertools.pairwise(lines):
            joins = (
                line.kind in TEXT_READ
                and _indented(line)
                and above.kind is line.kind
                and above.top + ROW_HEIGHT == line.top
            )
            if line.continues != joins:
                wrong.append(f"{entry.file} row {line.top}: continues {line.continues}")
    assert continued
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize(
    ("file", "whole"),
    [
        *[(f, "abcde" * 14) for f in _chat_frames(30, 31)],
        *[(f, "m" * 70) for f in _chat_frames(32, 33)],
    ],
)
def test_a_line_wrapped_mid_word_is_continued_with_no_space(
    frames: FrameSet, reader: ChatReader, file: str, whole: str
) -> None:
    """Our 70-letter test lines, wrapped 51 + 19 and 36 + 34 with no space at
    the break: the second row continues the first from the middle of a word."""
    head, rest = _read(frames, reader, file)[-2:]

    assert rest.continues
    assert rest.mid_word
    assert (rest.speaker, rest.message) == (None, None)
    assert head.message is not None
    assert rest.text is not None
    assert head.message + rest.text == whole


def test_a_line_wrapped_at_a_space_is_continued_after_it(
    frames: FrameSet, reader: ChatReader
) -> None:
    """Its next row's first letter would have fit on the row above: a space
    took its room (`WRAP_FITS`). The text isn't compared: it is a player's."""
    lines = _read(frames, reader, "henesyscrowd_1920x1080_000.png")
    [rest] = [line for line in lines if line.continues]

    assert not rest.mid_word


def test_a_line_on_one_row_of_70_letters_is_whole(
    frames: FrameSet, reader: ChatReader
) -> None:
    """70 letters fit on a row when they are narrow (`max_reply_chars`)."""
    for file in _chat_frames(34, 35):
        mine = [
            line
            for line in _read(frames, reader, file)
            if line.kind is ChatKind.GENERAL
        ]
        assert [line.message for line in mine] == ["i" * 70], file


# Our test lines, whispers and notices (v4).

TEST_LINES = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789",
    "abcdefghijklmnopqrstuvwxyz",
    "!\"#$%&'()*+,-./:;<=>?@",
    "[\\]^_`{|}~",
)
"""The four lines our character typed (chat_1920x1080_021 to _029 on general,
_036 to _043 whispered): every printable character between them."""


def test_the_test_lines_hold_every_printable_character() -> None:
    printable = set(string.printable) - set(string.whitespace) | {" "}

    assert set("".join(TEST_LINES)) | {" "} == printable


def _as_read(text: str) -> str:
    """`text` as the reader reads it: `l` is drawn as `I` is (`ALIKE`)."""
    for read, alike in ALIKE.items():
        for char in alike:
            text = text.replace(char, read)
    return text


@pytest.mark.parametrize(
    ("kind", "files"),
    [
        (ChatKind.GENERAL, _chat_frames(21, 29)),
        (ChatKind.WHISPER, _chat_frames(36, 43)),
    ],
    ids=["white", "green"],
)
def test_our_test_lines_read_whole_in_white_and_in_green(
    frames: FrameSet, reader: ChatReader, kind: ChatKind, files: list[str]
) -> None:
    """Every printable character, `_` among them, in each colour: no line of
    ours there reads otherwise, and each of the four is seen."""
    expected = {_as_read(text) for text in TEST_LINES}
    seen: set[str] = set()
    wrong: list[str] = []
    for file in files:
        for line in _read(frames, reader, file):
            if line.kind is not kind:
                continue
            if line.message not in expected:
                wrong.append(f"{file} row {line.top}: not a test line")
            elif kind is ChatKind.WHISPER and not line.outgoing:
                wrong.append(f"{file} row {line.top}: a whisper sent, not outgoing")
            else:
                seen.add(line.message)
    assert not wrong, "\n".join(wrong)
    assert seen == expected


_NOTICE = re.compile(rf"\[\d\d:\d\d\] {_as_read('Could not find')} \S+\.")


def test_under_each_whisper_to_someone_offline_is_a_notice_read_whole(
    frames: FrameSet, reader: ChatReader
) -> None:
    """`[hh:mm] Could not find <name>.`, a notice: never anyone's line, so
    never `general`, which the model would be asked to judge. The name isn't
    compared: it is a player's."""
    notices = 0
    for file in _chat_frames(36, 43):
        lines = _read(frames, reader, file)
        for above, line in itertools.pairwise(lines):
            if above.kind is not ChatKind.WHISPER:
                continue
            # Booleans only, so a failure prints no name.
            read_whole = line.text is not None and bool(_NOTICE.fullmatch(line.text))
            no_one_s = (line.speaker, line.message, line.outgoing) == (
                None,
                None,
                False,
            )
            assert line.kind is ChatKind.NOTICE, file
            assert read_whole, file
            assert no_one_s, file
            notices += 1
    assert notices == 12
