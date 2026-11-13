"""
The chat reader on the real MSCW frame set: every expected `chat` reading, and
the text of every general line.

The expected `chat` value is each visible line's kind, top to bottom. Each frame
is read by a reader that has forgotten the rows before, so every line shown is
new. The text isn't committed, because it holds other players' names: it is
labelled here by a render of Arial, as `toolkit/harvest_glyphs.py` labels it,
and compared with what the reader read with the harvested glyphs
(`python -m toolkit.harvest_glyphs`). Run with `pytest -m frames`.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.config import CONFIG, STORE
from maple.screen.chat import BAND_LEFT, BAND_RIGHT, CHAT, ChatKind, ChatReader
from maple.screen.font import CHAT_GENERAL
from maple.screen.locator import FrameCheck
from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites
from tests.frame_set import FrameSet
from toolkit import harvest_glyphs

pytestmark = [pytest.mark.frames, pytest.mark.client_files]


@pytest.fixture(scope="module")
def reader() -> ChatReader:
    sprites = load_reader_sprites(
        [FRAME_CHECK, CHAT],
        Profile(job="Swordsman"),
        STORE,
        config=CONFIG,
    )
    return ChatReader(sprites, FrameCheck(sprites))


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
    """The signature that tells a line from another is stable on the same
    pixels, whatever the line."""
    for entry in frames.entries:
        reader.forget()
        frame = _frame(frames, entry.file)
        if reader.read(frame).status is not Status.READ:
            continue
        again = reader.read(frame)
        assert again.value == [], entry.file


def test_every_general_line_reads_as_arial_labels_it(
    frames: FrameSet, reader: ChatReader
) -> None:
    """Text is compared with the labeller's, never committed. A general line
    with a character the harvest lacks reads `None`, never a shorter string."""
    if not harvest_glyphs.ARIAL.is_file():
        pytest.skip(f"the labelling font {harvest_glyphs.ARIAL} isn't on this machine")
    labeller = harvest_glyphs.font_labeller(harvest_glyphs.ARIAL)
    read = unread = 0
    wrong: list[str] = []
    for entry in frames.entries:
        reader.forget()
        frame = _frame(frames, entry.file)
        reading = reader.read(frame)
        region = reader.region(frame)
        for line in reading.value or []:
            if line.kind is not ChatKind.GENERAL:
                continue
            assert region is not None
            labelled = _labelled(frame, region.left, line.top, labeller)
            if line.text is None:
                unread += 1
            elif labelled is None or line.text.replace(" ", "") != labelled:
                wrong.append(f"{entry.file} row {line.top}: read text not the label")
            else:
                read += 1
    assert read
    assert not wrong, "\n".join(wrong)


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
