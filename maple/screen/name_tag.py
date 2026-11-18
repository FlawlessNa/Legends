"""
A character's name tag read with glyphs (#457, epic #455's D14): how the bot
tells its own character from other players' without OCR.

`read_name_tag(glyphs, pixels, client_size)` reads the tag nearest the middle
of `pixels`, a strip of the client under a character
(`maple.model.characters.own_character.tag_strip`):

1. The tag's text is found as `NameTagFinder` finds tags (`find_name_tags`).
2. Up to 1366x768 the tag is drawn 1:1, and its ink is its pure white
   (`font.NAME_TAG`). Above, the client draws the play area smaller and
   upscales it, which blends each pixel of the text with its neighbours:
   `unscale` undoes that first.
3. The text is read from its 11-row cell (`font.NAME_TAG`) with
   `GlyphSet.read_marked`, so a letter the set has no glyph for reads
   `UNREAD`. The cell starts at the text's top when the name holds a capital
   or a tall letter, and up to `CELL_RISE` rows above it when not: it is put
   where the fewest letters read `UNREAD`.

**Undoing the upscale.** The upscale is bilinear: each client pixel is a
blend of the two nearest play-area pixels on each axis, so a tag's client
pixels are `A_y @ tag @ A_x.T` for two known matrices (`_blend`) with more
rows than columns, and the tag is their least-squares solution,
`pinv(A_y) @ client @ pinv(A_x).T`. The matrices depend on where the tag sits
within a play-area pixel, which differs from tag to tag, and on the horizontal
scale, which on frame set `v4` is the client's width over the play area's on
some captures and its height over the play area's on others. So each is
tried (`OFFSETS`, `horizontal_scales`), and the solution kept is the one
that, made pure white and dark at `UNSCALED_WHITE`, explains the client's
pixels best. On `v4`'s ten name-tag frames at 1920x1080, our tag reads as our
name on all ten, and no other tag does. Under the labelled feet of `v4`'s 139
frames at 1920x1080, it reads so on 74 (35 of 58 at 1366x768, where nothing is
undone): on many of the others our tag isn't whole there (cut by the client's
edge, behind something, or joined to another's tag), which no reading can
help.

No value here is read from the client: `UNSCALED_WHITE` and `OFFSETS` were
chosen on frame set `v4`, and the play area's sizes are `camera.PLAY_AREAS`.
"""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from .font import NAME_TAG, UNREAD, GlyphSet
from .position.camera import play_area_size
from .position.characters import find_name_tags, tag_upscale
from .sprites import Declaration

NAME_TAGS = Declaration("name tag", glyph_sets=(NAME_TAG.name,))
"""What reading name tags needs: the `name-tag` glyphs, harvested from frames
(`python -m toolkit.harvest_glyphs`). A DecisionMaker that picks our character
by its tag names it in its `screen_readers`, so a missing set refuses the
start."""

ROWS = NAME_TAG.rows or 0
"""A tag's cell, in play-area rows (`font.NAME_TAG`)."""

CELL_RISE = 3
"""How many rows above the text's top a tag's cell may start: a name of
lowercase letters with no tall one starts 2 rows down its cell."""

OFFSETS = tuple(round(-0.5 + i / 10, 1) for i in range(10))
"""Where an upscaled tag may sit within a play-area pixel, in play-area px, on
each axis: every tenth of one."""

UNSCALED_WHITE = 190.0
"""An unscaled tag's pixel is ink from this lightest channel up, halfway
between the tag's dark box and its white. Under the labelled feet of `v4`'s
1920x1080 frames, our tag reads as our name on 71 at 170, 74 at 190 and 74
at 210."""

PAD = 8
"""Client px kept around an upscaled tag's text, so the text's edges are
solved from the pixels they are blended into."""


def read_name_tag(
    glyphs: GlyphSet, pixels: NDArray[np.uint8], client_size: tuple[int, int]
) -> str:
    """
    The name on the tag nearest the middle of `pixels` (BGR, a strip of a
    client of `client_size`), `UNREAD` for each letter `glyphs` lacks; empty
    when no tag is there, or the client's size wasn't measured
    (`camera.PLAY_AREAS`).
    """
    scale = tag_upscale(client_size)
    play_area = play_area_size(client_size)
    if scale is None or play_area is None:
        return ""
    boxes = find_name_tags(pixels, scale)
    if not boxes:
        return ""
    middle = pixels.shape[1] / 2
    x0, y0, x1, y1 = min(boxes, key=lambda b: abs((b[0] + b[2]) / 2 - middle))
    if scale == 1.0:
        top, left = max(0, y0 - CELL_RISE), max(0, x0 - 1)
        ink = NAME_TAG.ink(pixels[top : y0 + ROWS, left : x1 + 1])
        return _read_cell(glyphs, ink, y0 - top, 0, ink.shape[1], slack=0)
    top, left = max(0, y0 - PAD), max(0, x0 - PAD)
    window = pixels[top : y1 + PAD, left : x1 + PAD].astype(np.float64)
    lightest = np.minimum(np.minimum(window[..., 0], window[..., 1]), window[..., 2])
    ky = client_size[1] / play_area[1]
    unscaled, first_row, first_column, kx = unscale(
        lightest, horizontal_scales(client_size), ky
    )
    ink = unscaled >= UNSCALED_WHITE
    # The text's box, in the unscaled window's pixels.
    text_top = round((y0 - top + 0.5) / ky - 0.5) - first_row
    text_left = int(np.floor((x0 - left) / kx)) - first_column
    text_right = int(np.ceil((x1 - left) / kx)) - first_column
    return _read_cell(
        glyphs,
        ink,
        text_top,
        max(0, text_left - 1),
        min(ink.shape[1], text_right + 1),
        slack=1,
    )


def horizontal_scales(client_size: tuple[int, int]) -> tuple[float, ...]:
    """
    The horizontal scales a tag may be upscaled by at this size: the client's
    width over the play area's, and the vertical scale, its height over the
    play area's (on `v4`, a capture is upscaled by one or the other).
    Empty for a size not measured.
    """
    play_area = play_area_size(client_size)
    if play_area is None:
        return ()
    width, height = client_size
    return tuple(dict.fromkeys((width / play_area[0], height / play_area[1])))


def unscale(
    lightest: NDArray[np.float64], kxs: Sequence[float], ky: float
) -> tuple[NDArray[np.float64], int, int, float]:
    """
    The play-area pixels a window of an upscaled client was drawn from.

    :param lightest: The window's lightest channel.
    :param kxs: The horizontal scales to try (`horizontal_scales`).
    :param ky: The vertical scale.
    :returns: The pixels, the play-area row and column of their first one
        (relative to the window's first, which may be one before), and the
        horizontal scale kept.
    """
    height, width = lightest.shape
    rows = [_blend(height, ky, offset) for offset in OFFSETS]
    columns = [(*_blend(width, kx, offset), kx) for kx in kxs for offset in OFFSETS]
    row_inverses = [np.linalg.pinv(a) for a, _ in rows]
    column_inverses = [np.linalg.pinv(a) for a, _, _ in columns]
    best: tuple[float, NDArray[np.float64], int, int, float] | None = None
    for (ay, first_row), py in zip(rows, row_inverses, strict=True):
        partial = py @ lightest
        for (ax, first_column, kx), px in zip(columns, column_inverses, strict=True):
            solved = partial @ px.T
            two_tone = np.where(
                solved >= UNSCALED_WHITE, 255.0, np.minimum(solved, UNSCALED_WHITE)
            )
            error = float(np.abs(ay @ two_tone @ ax.T - lightest).mean())
            if best is None or error < best[0]:
                best = (error, solved, first_row, first_column, kx)
    assert best is not None, "no offset tried"
    _, solved, first_row, first_column, kx = best
    return solved, first_row, first_column, kx


def _blend(count: int, scale: float, offset: float) -> tuple[NDArray[np.float64], int]:
    """
    How `count` client px blend the play-area px under them, upscaled by
    `scale` with the play area shifted by `offset` of its px: one row per
    client px, one column per play-area px, the weights of a bilinear
    upscale. Also the play-area px of the first column.
    """
    at = (np.arange(count) + 0.5) / scale - 0.5 + offset
    below = np.floor(at).astype(int)
    first = int(below.min())
    weights = np.zeros((count, int(below.max()) + 2 - first))
    part = at - below
    weights[np.arange(count), below - first] += 1 - part
    weights[np.arange(count), below + 1 - first] += part
    return weights, first


def _read_cell(
    glyphs: GlyphSet,
    ink: NDArray[np.bool_],
    text_top: int,
    left: int,
    right: int,
    slack: int,
) -> str:
    """The text of the cell of `ink`'s columns `left` to `right` whose top
    reads the fewest `UNREAD` letters, of those from `CELL_RISE` (and
    `slack`) rows above `text_top` to `slack` rows below it."""
    best: tuple[tuple[int, int], str] | None = None
    for top in range(text_top - CELL_RISE - slack, text_top + slack + 1):
        if top < 0 or top >= ink.shape[0]:
            continue
        cell = np.zeros((ROWS, right - left), bool)
        part = ink[top : top + ROWS, left:right]
        cell[: part.shape[0]] = part
        if not cell.any():
            continue
        text = glyphs.read_marked(_drawn(cell))
        unread = text.count(UNREAD)
        key = (unread, unread - len(text))
        if best is None or key < best[0]:
            best = (key, text)
    return "" if best is None else best[1]


def _drawn(ink: NDArray[np.bool_]) -> NDArray[np.uint8]:
    """`ink` drawn as the tag's pure white on black, BGR."""
    pixels = np.zeros((*ink.shape, 3), np.uint8)
    pixels[ink] = 255
    return pixels
