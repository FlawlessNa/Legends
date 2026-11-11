"""
The chat reader on the real MSCW frame set: every expected `chat` reading, and
the text, speaker, message and `outgoing` of every general line.

The expected `chat` value is each visible line's kind, top to bottom. Each frame
is read by a reader that has forgotten the rows before, so every line shown is
new. The text isn't committed, because it holds other players' names: it is
labelled here by a render of Arial, as `toolkit/harvest_glyphs.py` labels it,
and compared with what the reader read with the harvested glyphs
(`python -m toolkit.harvest_glyphs`). The speaker and message are split from
that label too, so no name is committed either. Run with `pytest -m frames`.
"""

import re
from collections.abc import Iterator

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.chat import (
    ALIKE,
    BAND_LEFT,
    BAND_RIGHT,
    CHAT,
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


@pytest.fixture(scope="module")
def sprites() -> ReaderSprites:
    return load_reader_sprites(
        [FRAME_CHECK, CHAT],
        Profile(job="Swordsman", game_map="x"),
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


def _general_lines(
    frames: FrameSet, reader: ChatReader
) -> Iterator[tuple[str, ChatLine, str | None]]:
    """Every general line of the frame set: its frame, the line, and its label
    (`_labelled`)."""
    if not harvest_glyphs.ARIAL.is_file():
        pytest.skip(f"the labelling font {harvest_glyphs.ARIAL} isn't on this machine")
    labeller = harvest_glyphs.font_labeller(harvest_glyphs.ARIAL)
    for entry in frames.entries:
        reader.forget()
        frame = _frame(frames, entry.file)
        reading = reader.read(frame)
        region = reader.region(frame)
        for line in reading.value or []:
            if line.kind is not ChatKind.GENERAL:
                continue
            assert region is not None
            yield entry.file, line, _labelled(frame, region.left, line.top, labeller)


def test_every_general_line_reads_as_arial_labels_it(
    frames: FrameSet, reader: ChatReader
) -> None:
    """Text is compared with the labeller's, never committed. Every general
    line the labeller explains has its glyphs harvested, so none reads
    `UNREAD`; one it doesn't explain must still read, as some text."""
    read = 0
    wrong: list[str] = []
    for file, line, labelled in _general_lines(frames, reader):
        if line.text is None:
            wrong.append(f"{file} row {line.top}: a general line with no text")
        elif labelled is not None and line.text.replace(" ", "") != labelled:
            wrong.append(f"{file} row {line.top}: read text not the label")
        elif labelled is not None:
            read += 1
    assert read
    assert not wrong, "\n".join(wrong)


def test_every_general_line_has_the_speaker_and_message_its_label_has(
    frames: FrameSet, reader: ChatReader
) -> None:
    """The label is split by hand here: the time in brackets, then the name, up
    to the first `:`. The label has no spaces, so neither has what is compared."""
    split = 0
    wrong: list[str] = []
    for file, line, labelled in _general_lines(frames, reader):
        if labelled is None:
            continue
        expected = _label_split(labelled)
        got = (
            None
            if line.speaker is None or line.message is None
            else (line.speaker, line.message.replace(" ", ""))
        )
        if got != expected:
            wrong.append(f"{file} row {line.top}: split not as labelled")
        elif line.outgoing:
            wrong.append(f"{file} row {line.top}: outgoing for {NOBODY!r}")
        split += expected is not None
    assert split
    assert not wrong, "\n".join(wrong)


def test_a_line_is_outgoing_when_the_character_is_its_speaker(
    frames: FrameSet, sprites: ReaderSprites
) -> None:
    """Each frame's speakers, taken in turn as the character's name, in another
    case: their lines, and only theirs, are outgoing."""
    checked = 0
    wrong: list[str] = []
    for file, line, _ in _general_lines(
        frames, ChatReader(sprites, FrameCheck(sprites))
    ):
        if line.speaker is None:
            continue
        as_speaker = ChatReader(sprites, FrameCheck(sprites), ign=line.speaker.lower())
        reading = as_speaker.read(_frame(frames, file))
        assert reading.value is not None
        for other in reading.value:
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


def _label_split(labelled: str) -> tuple[str, str] | None:
    """The speaker and message of a label (no spaces): the time in brackets the
    client may put first, the name up to the first `:`, then the rest."""
    rest = _TIME.sub("", labelled, count=1) if labelled.startswith("[") else labelled
    speaker, colon, message = rest.partition(":")
    if not colon or not speaker.isalnum() or not message:
        return None
    return speaker, message


def _labelled(
    frame: Frame, x: int, top: int, labeller: dict[str, np.ndarray]
) -> str | None:
    """The line's text as the Arial render labels it, `I` for `I` and `l` alike,
    without spaces; `None` when the render doesn't explain every pixel. `x` is
    the chat's point."""
    cell_top = top + harvest_glyphs.CELL_OFFSET
    cell = frame.pixels[
        cell_top : cell_top + (CHAT_GENERAL.rows or 0), x + BAND_LEFT : x + BAND_RIGHT
    ]
    harvest = harvest_glyphs.harvest_lines([("line", CHAT_GENERAL.ink(cell))], labeller)
    if harvest.problems or not harvest.labels:
        return None
    return harvest.labels[0][1]
