"""Cut font-drawn glyphs out of the frame set into `data/glyphs/` (spec R4, #313).

    python -m toolkit.harvest_glyphs [--tag v1] [--labeller-font C:/Windows/Fonts/arial.ttf]

The glyphs are client pixels: they go to the gitignored `data/glyphs/`, which
`maple/screen/font.py` loads, and never into git. What to cut, and where, is in
`toolkit/glyph_sources/<tag>.json`, which holds no pixels:

- `chat-general`: general chat lines, each `[x, top of its 16-row band, width]`.
  They are **labelled by a render of Arial** at 14 px, unantialiased, which
  matches them exactly (#313). The render only labels: what is kept is the
  frame's own pixels, and nothing reads Arial afterwards. A line the render
  doesn't explain to the last pixel is refused. Arial draws `I` and `l` alike,
  so they are kept as one glyph, `I`, and the manifest says so.
- `countdown`: a buff slot's countdown rows, `[x, y, width, height]`, with the
  digits a person read there. Each digit is one blob of yellow ink; a box whose
  blobs don't number its digits is refused.

Every source is read back with the harvested set; any misread fails the run, and
nothing is written. The tool prints each source's labels for a person to check.
Needs the frames on disk (`python scripts/fetch_frames.py`); sends nothing to
the game.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import find_mask_glyphs
from maple.screen.font import (
    CHAT_GENERAL,
    COUNTDOWN,
    GLYPHS,
    GlyphSet,
    GlyphSetSpec,
    save_glyph_set,
)

REPO = Path(__file__).resolve().parents[1]
FRAMES_ROOT = REPO / "data" / "frames"
SOURCES = REPO / "toolkit" / "glyph_sources"
CURRENT = REPO / "tests" / "frames" / "CURRENT"
ARIAL = Path("C:/Windows/Fonts/arial.ttf")
LABELLER_SIZE = 14
CELL_OFFSET = 3
"""A chat line's glyph cell starts this many rows below its band's top
(`font.CHAT_GENERAL`)."""
MIN_BLOB = 3
"""Ink blobs smaller than this, in pixels, are specks, not digits."""

type Mask = NDArray[np.bool_]


@dataclass
class Harvest:
    """What a glyph set's sources gave: glyphs, where each came from, and why
    any source was refused."""

    glyphs: dict[str, Mask] = field(default_factory=dict[str, Mask])
    sources: dict[str, str] = field(default_factory=dict[str, str])
    problems: list[str] = field(default_factory=list[str])
    labels: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])

    def keep(self, char: str, mask: Mask, where: str, exact: bool) -> None:
        """Keep the first cut of each glyph. When `exact`, a later cut that
        differs is a problem."""
        kept = self.glyphs.get(char)
        if kept is None:
            self.glyphs[char] = mask
            self.sources[char] = where
        elif exact and (kept.shape != mask.shape or (kept != mask).any()):
            self.problems.append(
                f"{where}: {char!r} differs from its cut at {self.sources[char]}"
            )


# Chat: labelled by a font render.


def font_labeller(font: Path, size: int = LABELLER_SIZE) -> dict[str, Mask]:
    """Each printable ASCII character drawn by `font`, unantialiased, cut to its
    ink. Characters drawn alike are kept once, under the first."""
    from PIL import Image, ImageDraw, ImageFont

    face = ImageFont.truetype(str(font), size)
    drawn: dict[str, Mask] = {}
    for char in map(chr, range(0x21, 0x7F)):
        image = Image.new("L", (4 * size, 4 * size), 0)
        draw = ImageDraw.Draw(image)
        draw.fontmode = "1"
        draw.text((size, size), char, font=face, fill=255)
        ink = np.array(image) > 127
        ys, xs = np.nonzero(ink)
        drawn[char] = ink[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    return drawn


def alike(labeller: Mapping[str, Mask]) -> dict[str, str]:
    """Characters drawn alike: the first of each group -> the whole group."""
    groups: dict[tuple[tuple[int, ...], bytes], str] = {}
    for char, mask in labeller.items():
        key = (mask.shape, mask.tobytes())
        groups[key] = groups.get(key, "") + char
    return {group[0]: group for group in groups.values() if len(group) > 1}


def harvest_lines(
    lines: Iterable[tuple[str, Mask]], labeller: Mapping[str, Mask]
) -> Harvest:
    """
    Cut each line's glyphs, labelled by `labeller`.

    :param lines: Each line's name and its ink, one glyph cell high.
    :param labeller: The labelling font's glyphs, each cut to its ink.
    """
    groups = alike(labeller)
    distinct = {
        char: mask
        for char, mask in labeller.items()
        if not any(char in group and char != first for first, group in groups.items())
    }
    harvest = Harvest()
    for where, ink in lines:
        hits = find_mask_glyphs(ink, distinct, 0.0)
        explained = np.zeros_like(ink)
        cells: list[tuple[str, Mask]] = []
        for hit in hits:
            own = np.zeros((ink.shape[0], hit.width), bool)
            own[hit.y : hit.y + hit.height] = distinct[hit.name]
            explained[:, hit.x : hit.x + hit.width] |= own
            cells.append((hit.name, ink[:, hit.x : hit.x + hit.width]))
            if (ink[:, hit.x : hit.x + hit.width] != own).any():
                harvest.problems.append(
                    f"{where}: {hit.name!r} at x={hit.x} shares its columns with "
                    "another glyph's ink"
                )
        stray = int((ink & ~explained).sum())
        if stray:
            harvest.problems.append(
                f"{where}: {stray} ink pixel(s) no labelling glyph explains"
            )
            continue
        harvest.labels.append((where, "".join(name for name, _ in cells)))
        for name, cell in cells:
            harvest.keep(name, cell, where, exact=True)
    return harvest


# Countdown: labelled by a person.


def blobs(ink: Mask) -> list[Mask]:
    """Each blob of `ink` (8-connected, `MIN_BLOB` pixels or more), cut to
    its own box, left to right."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        ink.astype(np.uint8), connectivity=8
    )
    found: list[tuple[int, Mask]] = []
    for k in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[k])
        if area >= MIN_BLOB:
            found.append((x, labels[y : y + h, x : x + w] == k))
    return [mask for _, mask in sorted(found, key=lambda f: f[0])]


def harvest_digits(boxes: Iterable[tuple[str, Mask, str]]) -> Harvest:
    """
    Cut each box's digits, labelled by the text a person read there.

    :param boxes: Each box's name, its ink, and its text.
    """
    harvest = Harvest()
    for where, ink, text in boxes:
        found = blobs(ink)
        if len(found) != len(text):
            harvest.problems.append(
                f"{where}: {len(found)} blob(s) of ink for the {len(text)} "
                f"character(s) of {text!r}"
            )
            continue
        harvest.labels.append((where, text))
        for char, mask in zip(text, found, strict=True):
            harvest.keep(char, mask, where, exact=False)
    return harvest


def misreads(
    spec: GlyphSetSpec,
    harvest: Harvest,
    strips: Iterable[tuple[str, NDArray[np.uint8], str]],
) -> list[str]:
    """Each strip (name, BGR pixels, expected text) the harvested set misreads."""
    glyph_set = GlyphSet(spec, harvest.glyphs)
    wrong: list[str] = []
    for where, pixels, expected in strips:
        got = glyph_set.read(pixels)
        if got.replace(" ", "") != expected.replace(" ", ""):
            wrong.append(f"{where}: read {got!r}, labelled {expected!r}")
    return wrong


# The command.


def _load(directory: Path, frame: str) -> NDArray[np.uint8]:
    pixels = cv2.imread(str(directory / frame), cv2.IMREAD_COLOR)
    if pixels is None:
        sys.exit(
            f"{directory / frame} can't be read: run `python scripts/fetch_frames.py`"
        )
    return pixels.astype(np.uint8, copy=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--tag", default=None, help="frame set tag (tests/frames/CURRENT)"
    )
    parser.add_argument("--frames-root", type=Path, default=FRAMES_ROOT)
    parser.add_argument("--sources", type=Path, default=SOURCES)
    parser.add_argument("--out", type=Path, default=GLYPHS)
    parser.add_argument("--labeller-font", type=Path, default=ARIAL)
    args = parser.parse_args(argv)
    tag = args.tag or CURRENT.read_text(encoding="utf-8").strip()
    directory = args.frames_root / tag
    sources = json.loads((args.sources / f"{tag}.json").read_text(encoding="utf-8"))
    if not args.labeller_font.is_file():
        sys.exit(
            f"the labelling font {args.labeller_font} isn't there: pass --labeller-font"
        )

    lines: list[tuple[str, Mask]] = []
    line_strips: list[tuple[str, NDArray[np.uint8]]] = []
    rows = CHAT_GENERAL.rows or 0
    for source in sources.get(CHAT_GENERAL.name, []):
        x, top, width = source["line"]
        where = f"{source['frame']} line {top}"
        strip = _load(directory, source["frame"])[
            top + CELL_OFFSET : top + CELL_OFFSET + rows, x : x + width
        ]
        lines.append((where, CHAT_GENERAL.ink(strip)))
        line_strips.append((where, strip))
    labeller = font_labeller(args.labeller_font)
    chat = harvest_lines(lines, labeller)
    labelled = dict(chat.labels)
    chat.problems += misreads(
        CHAT_GENERAL,
        chat,
        [(w, s, labelled[w]) for w, s in line_strips if w in labelled],
    )

    boxes: list[tuple[str, Mask, str]] = []
    digit_strips: list[tuple[str, NDArray[np.uint8], str]] = []
    for source in sources.get(COUNTDOWN.name, []):
        x, y, w, h = source["box"]
        where = f"{source['frame']} box {x},{y}"
        strip = _load(directory, source["frame"])[y : y + h, x : x + w]
        boxes.append((where, COUNTDOWN.ink(strip), source["text"]))
        digit_strips.append((where, strip, source["text"]))
    digits = harvest_digits(boxes)
    digits.problems += misreads(COUNTDOWN, digits, digit_strips)

    for spec, harvest in ((CHAT_GENERAL, chat), (COUNTDOWN, digits)):
        print(
            f"{spec.name}: {len(harvest.glyphs)} glyph(s): {''.join(sorted(harvest.glyphs))}"
        )
        for where, text in harvest.labels:
            print(f"  {where}: {text}")
    problems = chat.problems + digits.problems
    if problems:
        print("\nNothing written:", *problems, sep="\n  ", file=sys.stderr)
        return 1
    for spec, harvest, same in (
        (
            CHAT_GENERAL,
            chat,
            {k: v for k, v in alike(labeller).items() if k in chat.glyphs},
        ),
        (COUNTDOWN, digits, {}),
    ):
        folder = save_glyph_set(spec, harvest.glyphs, harvest.sources, same, args.out)
        print(f"wrote {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
