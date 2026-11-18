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
  so they are kept as one glyph, `I`, and the manifest says so. Each glyph
  keeps Arial's bearings (the blank columns before and after its ink), which
  tell a space from the room a letter like `1` leaves around itself
  (`font.CHAT_GENERAL`): metrics of the font, not pixels. A line may give its
  `colour` (RGB, white when left out): the whisper's green is the same font,
  and a glyph cut in two colours must be the same both times. A line may
  instead give the `text` a person read there, for a letter the client draws
  unlike Arial (`A`, `K`, `#`): it is cut as `minimap-title` is, one letter per
  run of inked columns, and keeps Arial's bearings.
- `countdown`: a buff slot's countdown rows, `[x, y, width, height]`, with the
  digits a person read there. Each digit is one blob of yellow ink; a box whose
  blobs don't number its digits is refused.
- `minimap-title`: a line of the minimap banner's title, `[x, top of its
  capitals, width]`, with the text a person read there. Each letter is a run of
  columns holding ink; where two letters touch, `splits` gives the columns
  (from `x`) where the second one starts. A line whose runs don't number its
  letters is refused.

- `name-tag`: name tags on frames drawn 1:1 (up to 1366x768), each
  `[x, top of its 11-row cell, width]` (`font.NAME_TAG`). They are **labelled
  by Windows' GDI render of Arial** at 12 px, unantialiased, letters and digits
  only, which the client draws them with (#457): Pillow's render of the font
  draws `d` otherwise. A tag the render doesn't explain to the last pixel is
  refused; Arial draws `I` and `l` alike, kept as `I`, as for the chat. Needs
  Windows.

Every source is read back with the harvested set; any misread fails the run, and
nothing is written. The tool prints each source's labels for a person to check.
Needs the frames on disk (`python scripts/fetch_frames.py`); sends nothing to
the game.
"""

import argparse
import ctypes
import json
import string
import sys
from collections.abc import Iterable, Mapping, Sequence
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
    MINIMAP_TITLE,
    NAME_TAG,
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
NAME_TAG_FACE = "Arial"
NAME_TAG_SIZE = 12
"""The name tags' font and its size in px (`font.NAME_TAG`)."""
NAME_TAG_CHARACTERS = string.digits + string.ascii_uppercase + string.ascii_lowercase
"""What a name is made of. Uppercase before lowercase, so Arial's `I` and `l`
are kept as `I` (`alike`)."""

type Mask = NDArray[np.bool_]


@dataclass
class Harvest:
    """What a glyph set's sources gave: glyphs, where each came from, and why
    any source was refused."""

    glyphs: dict[str, Mask] = field(default_factory=dict[str, Mask])
    sources: dict[str, str] = field(default_factory=dict[str, str])
    problems: list[str] = field(default_factory=list[str])
    labels: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    forms: dict[str, list[tuple[Mask, str]]] = field(
        default_factory=dict[str, list[tuple[Mask, str]]]
    )
    """Each glyph's other forms, with where each was cut (`font.GlyphSet.forms`)."""

    def keep(
        self, char: str, mask: Mask, where: str, exact: bool, new_form: bool = False
    ) -> None:
        """Keep the first cut of each glyph. When `exact`, a later cut that
        differs is a problem, unless `new_form` (a person read it): then it is
        kept as another form of the glyph, when it is none of its forms yet."""
        kept = self.glyphs.get(char)
        if kept is None:
            self.glyphs[char] = mask
            self.sources[char] = where
            return
        if not exact:
            return
        known = [kept, *(form for form, _ in self.forms.get(char, []))]
        if any(_same(form, mask) for form in known):
            return
        if new_form:
            self.forms.setdefault(char, []).append((mask, where))
        else:
            self.problems.append(
                f"{where}: {char!r} differs from its cut at {self.sources[char]}"
            )


def _same(a: Mask, b: Mask) -> bool:
    return a.shape == b.shape and bool((a == b).all())


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


def font_bearings(font: Path, size: int = LABELLER_SIZE) -> dict[str, tuple[int, int]]:
    """Each printable ASCII character's bearings in `font`, unantialiased: the
    columns from where it is drawn to its ink, and from its ink to where the
    next character is drawn."""
    from PIL import Image, ImageDraw, ImageFont

    face = ImageFont.truetype(str(font), size)
    bearings: dict[str, tuple[int, int]] = {}
    for char in map(chr, range(0x21, 0x7F)):
        image = Image.new("L", (4 * size, 4 * size), 0)
        draw = ImageDraw.Draw(image)
        draw.fontmode = "1"
        draw.text((size, size), char, font=face, fill=255)
        xs = np.nonzero(np.array(image) > 127)[1]
        before = int(xs.min()) - size
        after = round(face.getlength(char)) - (int(xs.max()) + 1 - size)
        bearings[char] = (before, after)
    return bearings


def alike(labeller: Mapping[str, Mask]) -> dict[str, str]:
    """Characters drawn alike: the first of each group -> the whole group."""
    groups: dict[tuple[tuple[int, ...], bytes], str] = {}
    for char, mask in labeller.items():
        key = (mask.shape, mask.tobytes())
        groups[key] = groups.get(key, "") + char
    return {group[0]: group for group in groups.values() if len(group) > 1}


def harvest_lines(
    lines: Iterable[tuple[str, Mask]],
    labeller: Mapping[str, Mask],
    into: Harvest | None = None,
) -> Harvest:
    """
    Cut each line's glyphs, labelled by `labeller`.

    :param lines: Each line's name and its ink, one glyph cell high.
    :param labeller: The labelling font's glyphs, each cut to its ink.
    :param into: A harvest to add to, whose glyphs a cut must match; a new
        one when left out.
    """
    groups = alike(labeller)
    distinct = {
        char: mask
        for char, mask in labeller.items()
        if not any(char in group and char != first for first, group in groups.items())
    }
    harvest = Harvest() if into is None else into
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


# Name tags: labelled by Windows' GDI render.


def gdi_labeller(
    face: str = NAME_TAG_FACE,
    size: int = NAME_TAG_SIZE,
    characters: str = NAME_TAG_CHARACTERS,
) -> dict[str, Mask]:
    """
    Each of `characters` drawn by Windows' GDI in `face`, `size` px high (its
    em), unantialiased, cut to its ink: how the client draws its text (#457).

    :raises OSError: Not on Windows.
    """
    if sys.platform != "win32":
        raise OSError("the GDI labeller draws with Windows' GDI: run on Windows")
    from ctypes import wintypes

    gdi32 = ctypes.windll.gdi32
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    gdi32.CreateFontW.restype = wintypes.HFONT
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    gdi32.SetBkColor.argtypes = [wintypes.HDC, wintypes.DWORD]
    gdi32.TextOutW.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    class BitmapInfoHeader(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    side = 4 * size
    nonantialiased_quality = 3
    drawn: dict[str, Mask] = {}
    dc = gdi32.CreateCompatibleDC(None)
    # A negative height asks for the em, not the cell, to be `size` px.
    font = gdi32.CreateFontW(
        -size, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, nonantialiased_quality, 0, face
    )
    header = BitmapInfoHeader(
        ctypes.sizeof(BitmapInfoHeader), side, -side, 1, 32, 0, 0, 0, 0, 0, 0
    )
    bits = ctypes.c_void_p()
    bitmap = gdi32.CreateDIBSection(
        dc, ctypes.byref(header), 0, ctypes.byref(bits), None, 0
    )
    try:
        gdi32.SelectObject(dc, bitmap)
        gdi32.SelectObject(dc, font)
        gdi32.SetTextColor(dc, 0xFFFFFF)
        gdi32.SetBkColor(dc, 0)
        buffer = ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8))
        pixels = np.ctypeslib.as_array(buffer, shape=(side, side, 4))
        for char in characters:
            pixels[:] = 0
            gdi32.TextOutW(dc, size, size, char, 1)
            ink = pixels[..., 0] > 127
            ys, xs = np.nonzero(ink)
            drawn[char] = ink[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].copy()
    finally:
        gdi32.DeleteObject(font)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(dc)
    return drawn


def harvest_name_tags(
    tags: Iterable[tuple[str, NDArray[np.uint8]]], labeller: Mapping[str, Mask]
) -> Harvest:
    """
    Cut each name tag's glyphs, labelled by `labeller` (`gdi_labeller`), as a
    chat line's are (`harvest_lines`), then read each labelled tag back with
    the harvest, saying no text (`misreads`): a tag is another player's name.

    :param tags: Each tag's name, and the BGR pixels of its cell.
    """
    strips = list(tags)
    harvest = harvest_lines([(w, NAME_TAG.ink(p)) for w, p in strips], labeller)
    labelled = dict(harvest.labels)
    harvest.problems += misreads(
        NAME_TAG,
        harvest,
        [(w, p, labelled[w]) for w, p in strips if w in labelled],
        quiet=True,
    )
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


# Minimap title: labelled by a person, cut at the columns between letters.


def column_runs(ink: Mask, splits: Iterable[int] = ()) -> list[tuple[int, int]]:
    """
    Each run of columns of `ink` holding some ink, as `[start, end)`, left to
    right, cut again at every column in `splits` that falls inside one.
    """
    inked = ink.any(axis=0)
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, on in enumerate([*inked.tolist(), False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x))
            start = None
    for cut in sorted(splits):
        for i, (a, b) in enumerate(runs):
            if a < cut < b:
                runs[i : i + 1] = [(a, cut), (cut, b)]
                break
    return runs


def harvest_cut_lines(
    lines: Iterable[tuple[str, Mask, str, Sequence[int]]],
    into: Harvest | None = None,
    exact: bool = False,
) -> Harvest:
    """
    Cut each line's letters, labelled by the text a person read there: one
    letter per run of inked columns, as tall as the line's cell.

    :param lines: Each line's name, its ink (one cell high), its text, and the
        columns where touching letters are split.
    :param into: A harvest to add to; a new one when left out.
    :param exact: A later cut of a glyph must be one of its forms, or is kept
        as another form: a person read it (`Harvest.keep`).
    """
    harvest = Harvest() if into is None else into
    for where, ink, text, splits in lines:
        runs = column_runs(ink, splits)
        letters = text.replace(" ", "")
        if len(runs) != len(letters):
            harvest.problems.append(
                f"{where}: {len(runs)} run(s) of ink for the {len(letters)} "
                f"letter(s) of {text!r}"
            )
            continue
        harvest.labels.append((where, text))
        for char, (a, b) in zip(letters, runs, strict=True):
            harvest.keep(char, ink[:, a:b], where, exact=exact, new_form=exact)
    return harvest


def misreads(
    spec: GlyphSetSpec,
    harvest: Harvest,
    strips: Iterable[tuple[str, NDArray[np.uint8], str]],
    quiet: bool = False,
) -> list[str]:
    """Each strip (name, BGR pixels, expected text) the harvested set misreads.
    When `quiet`, the texts aren't said: a name tag's is another player's name."""
    forms = {c: [mask for mask, _ in f] for c, f in harvest.forms.items()}
    glyph_set = GlyphSet(spec, harvest.glyphs, forms=forms)
    wrong: list[str] = []
    for where, pixels, expected in strips:
        got = glyph_set.read(pixels)
        if got.replace(" ", "") != expected.replace(" ", ""):
            said = "" if quiet else f" {got!r}, labelled {expected!r}"
            wrong.append(f"{where}: read{said or ' otherwise than labelled'}")
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
    letters: list[tuple[str, Mask, str, Sequence[int]]] = []
    line_strips: list[tuple[str, GlyphSetSpec, NDArray[np.uint8]]] = []
    rows = CHAT_GENERAL.rows or 0
    for source in sources.get(CHAT_GENERAL.name, []):
        x, top, width = source["line"]
        colour = source.get("colour")
        spec = (
            CHAT_GENERAL
            if colour is None
            else CHAT_GENERAL.in_colour(
                (int(colour[0]), int(colour[1]), int(colour[2]))
            )
        )
        where = f"{source['frame']} line {top} x {x}"
        strip = _load(directory, source["frame"])[
            top + CELL_OFFSET : top + CELL_OFFSET + rows, x : x + width
        ]
        if "text" in source:
            ink = spec.ink(strip)
            letters.append((where, ink, source["text"], source.get("splits", [])))
        else:
            lines.append((where, spec.ink(strip)))
        line_strips.append((where, spec, strip))
    labeller = font_labeller(args.labeller_font)
    chat = harvest_lines(lines, labeller)
    harvest_cut_lines(letters, into=chat, exact=True)
    labelled = dict(chat.labels)
    for where, spec, strip in line_strips:
        if where in labelled:
            chat.problems += misreads(spec, chat, [(where, strip, labelled[where])])

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

    title_lines: list[tuple[str, Mask, str, Sequence[int]]] = []
    title_strips: list[tuple[str, NDArray[np.uint8], str]] = []
    rows = MINIMAP_TITLE.rows or 0
    for source in sources.get(MINIMAP_TITLE.name, []):
        x, top, width = source["line"]
        where = f"{source['frame']} title {top}"
        strip = _load(directory, source["frame"])[top : top + rows, x : x + width]
        splits = source.get("splits", [])
        title_lines.append((where, MINIMAP_TITLE.ink(strip), source["text"], splits))
        title_strips.append((where, strip, source["text"]))
    title = harvest_cut_lines(title_lines)
    title.problems += misreads(MINIMAP_TITLE, title, title_strips)

    tag_strips: list[tuple[str, NDArray[np.uint8]]] = []
    rows = NAME_TAG.rows or 0
    for source in sources.get(NAME_TAG.name, []):
        x, top, width = source["tag"]
        where = f"{source['frame']} tag {x},{top}"
        strip = _load(directory, source["frame"])[top : top + rows, x : x + width]
        tag_strips.append((where, strip))
    tag_labeller = gdi_labeller() if tag_strips else {}
    tags = harvest_name_tags(tag_strips, tag_labeller)

    harvests = (
        (CHAT_GENERAL, chat),
        (COUNTDOWN, digits),
        (MINIMAP_TITLE, title),
        (NAME_TAG, tags),
    )
    for spec, harvest in harvests:
        print(
            f"{spec.name}: {len(harvest.glyphs)} glyph(s): {''.join(sorted(harvest.glyphs))}"
        )
        if spec is NAME_TAG:
            # Other players' names: counted, never printed.
            print(f"  {len(harvest.labels)} of {len(tag_strips)} tag(s) labelled")
            continue
        for where, text in harvest.labels:
            print(f"  {where}: {text}")
    problems = chat.problems + digits.problems + title.problems + tags.problems
    if problems:
        print("\nNothing written:", *problems, sep="\n  ", file=sys.stderr)
        return 1
    bearings = font_bearings(args.labeller_font)
    for spec, harvest, same, spacing in (
        (
            CHAT_GENERAL,
            chat,
            {k: v for k, v in alike(labeller).items() if k in chat.glyphs},
            {k: v for k, v in bearings.items() if k in chat.glyphs},
        ),
        (COUNTDOWN, digits, {}, None),
        (MINIMAP_TITLE, title, {}, None),
        (
            NAME_TAG,
            tags,
            {k: v for k, v in alike(tag_labeller).items() if k in tags.glyphs},
            None,
        ),
    ):
        if not harvest.glyphs:
            print(f"{spec.name}: no source in {tag}, so its set is left as it was")
            continue
        folder = save_glyph_set(
            spec,
            harvest.glyphs,
            harvest.sources,
            same,
            args.out,
            spacing,
            harvest.forms,
        )
        print(f"wrote {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
