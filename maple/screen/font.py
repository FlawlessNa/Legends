"""
Font-drawn text: glyphs harvested from frames, labelled by a person, kept in
the gitignored `data/glyphs/` (spec R4).

**Why harvested** (#313). Glyphs rendered from the client's own font,
`UI/Font/NotoSansKRMedium.img`, match nothing on screen in frame set `v1`:

- the general chat lines are Arial at 14 px, unantialiased: a render of it
  matches every one exactly, and Noto at any size doesn't come close;
- the buff countdown's digits match no font at all, Noto or any font Windows
  ships, at any size: the best is a third of their pixels wrong.

So the glyphs come from the frames, cut by `toolkit/harvest_glyphs.py`. They are
client pixels, so they are never committed.

**A glyph set** (`GLYPH_SETS`) is one way text is drawn: which pixels are its ink
(`GlyphSetSpec.ink`), and how far a glyph may be from them. A glyph is a bool
mask; a strip of the screen is turned into ink, then read with
`botting.screen.read_mask_glyphs`, which compares each glyph's whole box, ink
and background. Exact sprite matching (`read_glyphs`) can't be used: the
countdown's yellow is blended with the icon under it, so its colours never
repeat, and a chat glyph's ink alone fits inside other glyphs.

On disk, a set is a folder of one PNG per glyph (ink white, background black)
and a `manifest.json` naming each glyph's character, its file, and where it was
cut from. `load_glyph_set` reads it; `GlyphsMissing` says how to make it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from botting.screen import find_mask_glyphs, read_mask_glyphs

REPO = Path(__file__).resolve().parents[2]
GLYPHS = REPO / "data" / "glyphs"
"""Where harvested glyph sets are kept: gitignored, like all of `data/`."""

MANIFEST = "manifest.json"

type RGB = tuple[int, int, int]


class GlyphsMissing(LookupError):
    """A glyph set isn't on disk, or is incomplete. Says how to make it."""


@dataclass(frozen=True, slots=True)
class GlyphSetSpec:
    """
    How one glyph set is drawn and read.

    :ivar name: Its folder under `GLYPHS`.
    :ivar low: The darkest ink, per channel, in RGB.
    :ivar high: The brightest ink, per channel, in RGB. A pixel is ink when
        each of its channels is within `low` and `high`.
    :ivar max_error: The share of a glyph's box that may differ from the ink.
    :ivar space_gap: Columns between two glyphs that read as a space, or
        `None` when the text has no spaces.
    :ivar rows: The height of every glyph, when the set's glyphs are cut as
        whole cells of a line (so a glyph keeps its height above the baseline);
        `None` when each is cut to its own ink.
    """

    name: str
    low: RGB
    high: RGB
    max_error: float
    space_gap: int | None = None
    rows: int | None = None

    def ink(self, pixels: NDArray[np.uint8]) -> NDArray[np.bool_]:
        """Which of `pixels` (`H x W x 3`, BGR, as captured) are this set's ink."""
        bgr_low = np.array(self.low[::-1], np.uint8)
        bgr_high = np.array(self.high[::-1], np.uint8)
        return ((pixels >= bgr_low) & (pixels <= bgr_high)).all(axis=2)


CHAT_GENERAL = GlyphSetSpec(
    "chat-general",
    low=(255, 255, 255),
    high=(255, 255, 255),
    max_error=0.0,
    space_gap=3,
    rows=14,
)
"""General chat lines: pure white, unantialiased, so read exactly. A line's
cell is its 14 rows starting 3 below the top of its 16-row band, which holds
every glyph from 11 rows above the baseline to 2 below it, and none of the next
line's. A gap of 3 columns or more is a space (frame set `v1`)."""

COUNTDOWN = GlyphSetSpec(
    "countdown",
    low=(0x81, 0x71, 0x00),
    high=(0xFF, 0xFF, 0x3F),
    max_error=0.12,
)
"""A buff's seconds left: yellow digits in a dark outline, antialiased, their
fill blended with the icon under them. Ink is their brighter yellow. On frame
set `v1` (f007-f014), the same digit cut from another slot and frame differed
from its glyph by at most 0.074 of its box; the nearest wrong digit, at the
same place, by 0.083 or more, and always by more than the right one."""

MINIMAP_TITLE = GlyphSetSpec(
    "minimap-title",
    low=(170, 170, 170),
    high=(255, 255, 255),
    max_error=0.08,
    space_gap=3,
    rows=12,
)
"""The minimap banner's street and map name: white, antialiased and drawn
twice a column apart (bold), with a dark shadow a pixel down and right, on the
banner's (153, 187, 204). Ink is every channel 170 or more, which the banner
and the shadow never reach. A line's cell is the 12 rows from the top of its
capitals, which hold its descenders. On frame set `v2`, letters are 1 or 2
columns apart and words 4 (#387). Not the client's font: a render of
`UI/Font/NotoSansKRMedium.img` at 11 px, drawn twice a column apart, is as wide
as "Dungeon" but gets 73 of its 179 ink pixels wrong, so the glyphs are
harvested (R4)."""

GLYPH_SETS: dict[str, GlyphSetSpec] = {
    s.name: s for s in (CHAT_GENERAL, COUNTDOWN, MINIMAP_TITLE)
}


@dataclass(frozen=True, slots=True)
class GlyphSet:
    """
    A glyph set, in memory.

    :ivar glyphs: Each glyph's character -> its bool mask.
    :ivar alike: Characters drawn the same, so read as one: the glyph's
        character -> every character it may be (Arial draws `I` and `l` alike).
    """

    spec: GlyphSetSpec
    glyphs: Mapping[str, NDArray[np.bool_]]
    alike: Mapping[str, str] = field(default_factory=dict[str, str])

    def read(self, pixels: NDArray[np.uint8]) -> str:
        """The text drawn in `pixels` (BGR). A glyph the set lacks is left out."""
        return read_mask_glyphs(
            self.spec.ink(pixels), self.glyphs, self.spec.max_error, self.spec.space_gap
        )

    def read_all(self, pixels: NDArray[np.uint8]) -> str | None:
        """The text drawn in `pixels` (BGR), or `None` when some of its ink isn't
        a glyph of the set: never a string with characters missing."""
        ink = self.spec.ink(pixels)
        hits = find_mask_glyphs(ink, self.glyphs, self.spec.max_error)
        explained = np.zeros_like(ink)
        for hit in hits:
            glyph = self.glyphs[hit.name]
            explained[hit.y : hit.y + hit.height, hit.x : hit.x + hit.width] |= glyph
        if (ink & ~explained).any():
            return None
        text: list[str] = []
        gap = self.spec.space_gap
        for previous, hit in zip([None, *hits], hits, strict=False):
            if (
                previous is not None
                and gap is not None
                and hit.x - (previous.x + previous.width) >= gap
            ):
                text.append(" ")
            text.append(hit.name)
        return "".join(text)


def glyph_file(char: str) -> str:
    """The file name a character's glyph is kept under: its code point."""
    return f"U+{ord(char):04X}.png"


def save_glyph_set(
    spec: GlyphSetSpec,
    glyphs: Mapping[str, NDArray[np.bool_]],
    sources: Mapping[str, object],
    alike: Mapping[str, str] | None = None,
    root: Path = GLYPHS,
) -> Path:
    """
    Write a glyph set under `root`, replacing any there.

    :param sources: Each glyph's character -> where it was cut from, kept in
        the manifest for a person checking the labels.
    :returns: The set's folder.
    """
    folder = root / spec.name
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("U+*.png"):
        old.unlink()
    entries: dict[str, dict[str, object]] = {}
    for char, mask in sorted(glyphs.items()):
        _check(spec, char, mask)
        name = glyph_file(char)
        if not cv2.imwrite(str(folder / name), mask.astype(np.uint8) * 255):
            raise OSError(f"can't write {folder / name}")
        entries[char] = {"file": name, "source": sources.get(char)}
    manifest = {"set": spec.name, "glyphs": entries, "alike": dict(alike or {})}
    (folder / MANIFEST).write_text(
        json.dumps(manifest, indent=1, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return folder


def load_glyph_set(name: str, root: Path = GLYPHS) -> GlyphSet:
    """
    A harvested glyph set.

    :raises KeyError: `name` isn't in `GLYPH_SETS`.
    :raises GlyphsMissing: It isn't under `root`, or a file it lists is missing
        or malformed.
    """
    spec = GLYPH_SETS[name]
    folder = root / name
    hint = (
        f"fetch the frame set (`python scripts/fetch_frames.py`), then run "
        f"`python -m toolkit.harvest_glyphs` to cut them into {root}"
    )
    try:
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GlyphsMissing(f"the {name!r} glyphs aren't in {folder}: {hint}") from None
    except json.JSONDecodeError as error:
        raise GlyphsMissing(
            f"{folder / MANIFEST} is malformed ({error}): {hint}"
        ) from None
    glyphs: dict[str, NDArray[np.bool_]] = {}
    for char, entry in manifest.get("glyphs", {}).items():
        path = folder / str(entry["file"])
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise GlyphsMissing(f"{path} can't be read: {hint}")
        mask = image > 127
        try:
            _check(spec, char, mask)
        except ValueError as error:
            raise GlyphsMissing(f"{path}: {error}: {hint}") from None
        glyphs[char] = mask
    if not glyphs:
        raise GlyphsMissing(f"{folder / MANIFEST} lists no glyph: {hint}")
    alike = {str(k): str(v) for k, v in manifest.get("alike", {}).items()}
    return GlyphSet(spec, glyphs, alike)


def _check(spec: GlyphSetSpec, char: str, mask: NDArray[np.bool_]) -> None:
    if len(char) != 1:
        raise ValueError(f"a glyph is one character, not {char!r}")
    if mask.ndim != 2 or not mask.any():
        raise ValueError(f"the glyph for {char!r} has no ink")
    if spec.rows is not None and mask.shape[0] != spec.rows:
        raise ValueError(
            f"the glyph for {char!r} is {mask.shape[0]} rows, not {spec.rows}"
        )
