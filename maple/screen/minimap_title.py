"""
The minimap banner's title: the street and the map's name, read with glyphs
harvested from the frames (`font.MINIMAP_TITLE`, #387) and matched to the
catalogue's map names.

**Where it is drawn.** Only the expanded look with the banner (`MaxMap`)
draws it (`MinimapView.banner`). The map's mark, a 38x38 sprite from
`Map/MapHelper.img/mark`, is drawn at `MARK` from the frame's top-left, and
the title right of it, up to the map area's right edge, in two lines: the
street, then the map's name. The lines aren't at fixed rows: on frame set
`v2`, Damp Forest's capitals start 30 rows below the frame's top and
Ellinia's 31, likely because the client centres the two lines on their ink
and Ellinia's have no descenders. So the lines are found by their ink: rows of
title ink beside the mark, apart by at least one row without any, each read in
a cell of `MINIMAP_TITLE.rows` from its first inked row.

**What it reads as.** `READ`, with the catalogue's own spelling
(`street: map name`), when exactly two lines are read whole and a map is
called that; spaces are left out of the comparison, since the gap between two
words is only a few columns wider than the gap between two letters. `UNSURE`
when the banner isn't shown (`MinMap`, minimised), when there aren't two
lines, when some ink isn't a harvested glyph (a letter the frames haven't
shown yet), or when no map is called what was read. Any other status is the
minimap's.

The harvested glyphs are only the letters frame set `v2` shows (its two maps'
titles), so another map's title reads `UNSURE` until frames of it are
harvested.
"""

from collections.abc import Iterable

import numpy as np

from botting.screen import Frame, Reading
from botting.utilities import Box

from .font import MINIMAP_TITLE, GlyphSet
from .minimap import MinimapReader, MinimapView
from .sprites import Declaration, ReaderSprites

MINIMAP_TITLE_READER = Declaration("minimap title", glyph_sets=(MINIMAP_TITLE.name,))
"""The title's glyphs. The frame is found by the minimap reader, whose sprites
`minimap.MINIMAP` declares."""

MARK = Box(left=7, right=45, top=22, bottom=60)
"""Where the map's mark is drawn, from the frame's top-left. Seen on frame set
`v2` (both maps, every client size); the title starts right of it, and its
lines lie between its top and bottom."""


def _key(title: str) -> str:
    return title.replace(" ", "")


class MinimapTitleReader:
    """
    Reads the minimap banner's title. One per bot, built at start.

    :param titles: Every map's name as the catalogue spells it,
        `street: map name`. A title read is one of them, or `UNSURE`.
    """

    def __init__(
        self, sprites: ReaderSprites, minimap: MinimapReader, titles: Iterable[str]
    ) -> None:
        self._glyphs: GlyphSet = sprites.glyph_set(MINIMAP_TITLE.name)
        self._minimap = minimap
        self._titles = {_key(title): title for title in titles}

    def read(self, frame: Frame) -> Reading[str]:
        """The title in `frame`. Never raises because of what is on screen."""
        minimap = self._minimap.read(frame)
        if minimap.value is None:
            return Reading(None, minimap.status, minimap.frame_time, minimap.detail)
        return self.read_view(frame, minimap.value)

    def read_view(self, frame: Frame, view: MinimapView) -> Reading[str]:
        """The title in `frame`, whose minimap was read as `view`."""
        at = frame.captured_at
        if view.banner is None or view.map_area is None:
            return Reading.unsure(at, "the minimap shows no banner")
        lines = self._lines(frame.pixels, view.banner, view.map_area.right)
        if isinstance(lines, str):
            return Reading.unsure(at, lines)
        street, name = lines
        title = f"{street}: {name}"
        known = self._titles.get(_key(title))
        if known is None:
            return Reading.unsure(at, f"read {title!r}, which no map is called")
        return Reading.read(known, at)

    def _lines(
        self, pixels: np.ndarray, banner: Box, right: int
    ) -> tuple[str, str] | str:
        """The two lines' text, or why they can't be read."""
        top, bottom = banner.top + MARK.top, banner.top + MARK.bottom
        left = banner.left + MARK.right
        block = pixels[top:bottom, left:right]
        runs = _runs(MINIMAP_TITLE.ink(block).any(axis=1))
        if len(runs) != 2:
            return f"{len(runs)} line(s) of title, not 2"
        rows = MINIMAP_TITLE.rows or 0
        read: list[str] = []
        for start, end in runs:
            if end - start > rows or start + rows > len(block):
                return "a line of title is taller than its cell"
            text = self._glyphs.read_all(block[start : start + rows])
            if text is None:
                return "a letter of the title isn't among the harvested glyphs"
            read.append(text)
        return read[0], read[1]


def _runs(inked: np.ndarray) -> list[tuple[int, int]]:
    """Each run of `True` in `inked`, as `[start, end)`."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for y, on in enumerate([*inked.tolist(), False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            runs.append((start, y))
            start = None
    return runs
