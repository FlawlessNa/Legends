"""
Name tags read with the harvested `name-tag` glyphs on the real MSCW frame set
(#457), as `OwnCharacterPicker` reads them: each tag from the strip that a
character's box, 40 play-area px wide and ending at the feet over the tag,
cuts under it (`tag_strip`).

- Our tag reads as our name on every name-tag frame (`v4`'s 20, at 1366x768
  and 1920x1080), and no other tag does.
- Every tag on those frames at 1366x768 that Windows' GDI render of Arial
  labels (`toolkit.harvest_glyphs.gdi_labeller`), 61 of the 83 found, reads
  as labelled, so none reads `UNREAD`. The render doesn't label the others:
  something drawn over them, or a letter beside theirs, adds ink no letter
  explains.

No other player's name is committed or printed: their tags are compared with
the render's label, as the chat's lines are (`test_screen_chat_frames.py`).
The upscaled tags at 1920x1080 have no such label: the render labels the
client's pixels, and there they are blended. Run with `pytest -m frames`, after
`python -m toolkit.harvest_glyphs`.
"""

import collections
import sys
from collections.abc import Iterator

import numpy as np
import pytest
from numpy.typing import NDArray

from maple.model.characters.own_character import NameTagReader, tag_strip
from maple.screen.font import NAME_TAG, load_glyph_set
from maple.screen.position import tag_upscale
from maple.screen.position.characters import (
    STATUS_BAR_ROWS,
    TAG_TO_FEET,
    Box,
    find_name_tags,
)
from tests.frame_set import FrameSet
from toolkit import harvest_glyphs

pytestmark = [pytest.mark.frames]

OURS = "Mangoose"
"""Our character's name on the frame set (`test_screen_characters.py`)."""

NAME_TAG_FRAMES = "nametags_"
CHARACTER_WIDTH = 40
"""A character's box, in play-area px (`test_own_character.py`'s)."""

DARK = 90
"""A tag box's brightest channel at most, at 1:1 (`characters._dark`)."""


@pytest.fixture(scope="module")
def reader() -> NameTagReader:
    return NameTagReader(load_glyph_set(NAME_TAG.name))


def _tags(
    frames: FrameSet,
) -> Iterator[tuple[str, tuple[int, int], Box, NDArray[np.uint8], NDArray[np.uint8]]]:
    """Each tag found on the name-tag frames: its frame, the client's size,
    its text's box, the frame's pixels, and the strip `tag_strip` cuts under a
    character standing over it."""
    for entry in frames.entries:
        if not entry.file.startswith(NAME_TAG_FRAMES):
            continue
        pixels = frames.pixels(entry)
        scale = tag_upscale(entry.client_size)
        assert scale is not None, entry.client_size
        for box in find_name_tags(pixels[:-STATUS_BAR_ROWS], scale):
            x0, y0, x1, _ = box
            centre, half = (x0 + x1) / 2, CHARACTER_WIDTH * scale / 2
            feet = y0 - round(TAG_TO_FEET * scale)
            character = (round(centre - half), 0, round(centre + half), feet)
            strip = tag_strip(pixels, character, scale)
            assert strip is not None, (entry.file, box)
            yield entry.file, entry.client_size, box, pixels, strip


def _label(
    pixels: NDArray[np.uint8], box: Box, labeller: dict[str, NDArray[np.bool_]]
) -> str | None:
    """
    The render's label of the 1:1 tag whose text is `box`, cut as the harvest's
    sources are (`toolkit/glyph_sources/v4.json`): its cell from 3 rows below
    its dark box's top, a column wider each side; None where the render doesn't
    explain it to the last pixel.
    """
    x0, y0, x1, _ = box
    top = y0
    while top > y0 - 6 and (pixels[top - 1, x0:x1].max(axis=1) <= DARK).mean() >= 0.5:
        top -= 1
    cell = pixels[top + 3 : top + 3 + (NAME_TAG.rows or 0), x0 - 2 : x1 + 2]
    harvest = harvest_glyphs.harvest_lines([("tag", NAME_TAG.ink(cell))], labeller)
    return harvest.labels[0][1] if harvest.labels else None


def test_our_tag_reads_as_our_name_on_every_name_tag_frame(
    frames: FrameSet, reader: NameTagReader
) -> None:
    ours: collections.Counter[str] = collections.Counter()
    sizes: set[tuple[int, int]] = set()
    for file, size, _, _, strip in _tags(frames):
        sizes.add(size)
        ours[file] += reader.read_tag(strip, size) == OURS
    files = {e.file for e in frames.entries if e.file.startswith(NAME_TAG_FRAMES)}
    assert len(files) == 20
    assert sizes == {(1366, 768), (1920, 1080)}
    wrong = [
        f"{f}: {ours[f]} tags read as our name" for f in sorted(files) if ours[f] != 1
    ]
    assert not wrong, "\n".join(wrong)


@pytest.mark.skipif(sys.platform != "win32", reason="labels with Windows' GDI")
def test_every_tag_the_render_labels_reads_as_labelled(
    frames: FrameSet, reader: NameTagReader
) -> None:
    labeller = harvest_glyphs.gdi_labeller()
    labelled = 0
    wrong: list[str] = []
    for file, size, box, pixels, strip in _tags(frames):
        if tag_upscale(size) != 1.0:
            continue
        label = _label(pixels, box, labeller)
        if label is None:
            continue
        labelled += 1
        if reader.read_tag(strip, size) != label:
            wrong.append(f"{file}: the tag at {box[:2]} reads otherwise than labelled")
    assert labelled
    assert not wrong, "\n".join(wrong)


def test_the_harvested_set_draws_i_and_l_alike_as_the_reader_folds_them() -> None:
    glyphs = load_glyph_set(NAME_TAG.name)
    assert glyphs.alike == {"I": "Il"}
    reader = NameTagReader(glyphs)
    assert reader.fold("Il") == reader.fold("lI")
