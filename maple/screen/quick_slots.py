"""
The quick slots: each slot's key label found by its own sprite, then the item
count drawn in the slot read with the client's digit sprites.

**Labels.** Every key's label, `UI/QuickSlot.img/key/<name>`, is its own anchor:
it is searched for on its own, and where it was found is remembered. Once any
were found, later frames re-check just those spots, and a label found earlier
that no longer matches makes the reading `COVERED`. The slot background isn't
an anchor (its alpha is 0 to 39).

**Grid.** A slot's `row` and `column` (from 1) are counted from the labels'
positions: labels that start within `SAME_LINE` pixels of each other are one
row, likewise one column. They are the numbering of `QuickSlots.slot`, so an
entire first row or column with no label found would shift it.

**Counts.** No sprite origin or `vector:` node gives where a count is drawn
relative to its label: the labels' and `UI/Basic.img/ItemNo` digits' origins are
all `(0, 0)`, and `UI/QuickSlot.img`'s vectors place neither. So no offset is
used. Digit runs are searched for in the slots' area, and each run belongs to
the slot whose label is the nearest one at or above it, in its column. A slot
with no run has `count` `None`. A run that clearly belongs to no slot (no label
there, farther from its label than the labels' own spacing, or two runs for one
slot) makes the reading `UNSURE`, not a guess.

A run that starts within `SAME_LINE` of a label's top is beside the label, not
under it, and isn't a count: it is a cooldown number, which the client draws
with the same digits at the slot's top right while the slot recharges. It is
skipped, and the slot keeps the count drawn below.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from botting.screen import Frame, Reading, match

from .locator import FrameCheck
from .sprites import Declaration, ReaderSprites

_KEY = "UI/QuickSlot.img/key"
_ITEM_NO = "UI/Basic.img/ItemNo"

KEY_NAMES = (
    *(str(n) for n in (*range(1, 14), *range(16, 28), *range(29, 53))),
    *("56", "57", "59", "60", "61", "62", "63", "64", "65", "66", "67", "68"),
    *("70", "71", "73", "79", "81", "82", "83", "87", "88"),
    "Psc",
    "Brk",
)
"""The nodes of `UI/QuickSlot.img/key`, as the client names them."""

DIGITS = tuple(str(n) for n in range(10))

COLUMNS = 4
"""Slots per row of the layout, the numbering of `configs/keybindings.ini`'s
`Quick slots`: row-major from 1."""

SAME_LINE = 12
"""Labels whose top-left corners are closer than this are in the same row or
column: the tallest label is 12 pixels high, and slots are well over twice that
apart."""

RUN_GAP = 2
"""Digits no further apart than this, in pixels, are one count. Provisional:
chosen without frames of counts."""

_SAMPLES = 8
"""How many of a label's opaque pixels the first pass checks."""
_FEW = 64
"""The first pass stops early once this few positions remain."""

QUICK_SLOTS = Declaration(
    "quick slots",
    canvases=(
        *(f"{_KEY}/{name}" for name in KEY_NAMES),
        *(f"{_ITEM_NO}/{digit}" for digit in DIGITS),
    ),
)


@dataclass(frozen=True, slots=True)
class Slot:
    """
    One quick slot whose label was found.

    :ivar row: From 1, counted from the labels found.
    :ivar column: Likewise.
    :ivar key: The label's node name under `UI/QuickSlot.img/key`.
    :ivar count: The item count drawn, or `None` when none is.
    :ivar x: The label's top-left corner, in client pixels.
    :ivar y: Likewise.
    """

    row: int
    column: int
    key: str
    count: int | None
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class QuickSlots:
    """The slots whose labels were found, row by row."""

    slots: tuple[Slot, ...]

    def slot(self, n: int) -> Slot | None:
        """
        The slot numbered `n` in `configs/keybindings.ini`'s `Quick slots`
        setting: 1-based, row-major, `COLUMNS` to a row. `None` when its label
        wasn't found.

        :raises ValueError: `n` is below 1.
        """
        if n < 1:
            raise ValueError(f"quick slots are numbered from 1, not {n}")
        row, column = divmod(n - 1, COLUMNS)
        for slot in self.slots:
            if (slot.row, slot.column) == (row + 1, column + 1):
                return slot
        return None


@dataclass(frozen=True, slots=True)
class _Run:
    """Digits drawn together: where they start, their centre, and their value."""

    top: int
    centre: int
    value: int


class QuickSlotsReader:
    """
    Reads the quick slots. One per bot, sharing its `FrameCheck`; it remembers
    where the labels were found until the client's size changes.
    """

    def __init__(
        self, sprites: ReaderSprites, frame_check: FrameCheck, tolerance: float = 0.5
    ) -> None:
        self._frame_check = frame_check
        self._tolerance = tolerance
        self._labels = {name: sprites.canvas(f"{_KEY}/{name}") for name in KEY_NAMES}
        self._digits = {d: sprites.canvas(f"{_ITEM_NO}/{d}") for d in DIGITS}
        self._found: dict[str, tuple[int, int]] = {}
        self._client_size: tuple[int, int] | None = None

    def read(self, frame: Frame) -> Reading[QuickSlots]:
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        pixels = frame.pixels
        if frame.client_size != self._client_size:
            self._client_size = frame.client_size
            self._found = {}
        if not self._found:
            self._found = self._search(pixels)
            if not self._found:
                return Reading.absent(frame.captured_at, "no key label found")
        else:
            moved = [
                name
                for name, at in self._found.items()
                if not self._at(pixels, name, at)
            ]
            if moved:
                return Reading.covered(
                    frame.captured_at,
                    "label not where it was found: " + ", ".join(moved),
                )
        return self._counts(frame)

    def _at(self, pixels: np.ndarray, name: str, at: tuple[int, int]) -> bool:
        rgba = self._labels[name].rgba
        h, w = rgba.shape[:2]
        hits = match(pixels, rgba, (at[0], at[1], w, h), self._tolerance)
        return any((hit.x, hit.y) == at for hit in hits)

    def _search(self, pixels: np.ndarray) -> dict[str, tuple[int, int]]:
        """
        Every label found in `pixels`. Where a label overlaps another found
        one, the one with fewer opaque pixels is dropped: a short label like
        `S` can match inside the drawing of `Shift`, which is the better
        evidence.
        """
        packed = _pack(pixels)
        found: dict[str, tuple[int, int]] = {}
        for name, label in self._labels.items():
            at = self._find(pixels, packed, label.rgba)
            if at is not None:
                found[name] = at

        def rect(name: str) -> tuple[int, int, int, int]:
            h, w = self._labels[name].rgba.shape[:2]
            return (*found[name], w, h)

        def strength(name: str) -> int:
            return int((self._labels[name].rgba[:, :, 3] == 255).sum())

        for name in sorted(found, key=strength):
            if any(
                other != name
                and strength(other) >= strength(name)
                and _overlap(rect(name), rect(other))
                for other in found
            ):
                del found[name]
        return found

    def _find(
        self, pixels: np.ndarray, packed: np.ndarray, rgba: np.ndarray
    ) -> tuple[int, int] | None:
        """
        Where `rgba` is best matched in `pixels`. Searching the whole frame with
        a mask is slow, so first keep the positions where a handful of its
        opaque pixels are drawn exactly (a match within tolerance is nearly
        exact), then match only there.
        """
        h, w = rgba.shape[:2]
        rows, cols = packed.shape
        if rows < h or cols < w:
            return None
        ys, xs = np.nonzero(rgba[:, :, 3] == 255)
        if len(ys) == 0:
            return None
        sample = np.unique(np.linspace(0, len(ys) - 1, _SAMPLES).astype(int))
        candidates = np.ones((rows - h + 1, cols - w + 1), dtype=bool)
        for i in sample:
            y, x = int(ys[i]), int(xs[i])
            r, g, b = (int(v) for v in rgba[y, x, :3])
            same = packed[y : y + rows - h + 1, x : x + cols - w + 1] == (
                (b << 16) | (g << 8) | r
            )
            candidates &= same
            if int(candidates.sum()) <= _FEW:
                break
        best: tuple[float, int, int] | None = None
        for cy, cx in zip(*np.nonzero(candidates), strict=True):
            for hit in match(pixels, rgba, (int(cx), int(cy), w, h), self._tolerance):
                if (hit.x, hit.y) == (int(cx), int(cy)) and (
                    best is None or hit.error < best[0]
                ):
                    best = (hit.error, hit.x, hit.y)
        return None if best is None else (best[1], best[2])

    def _counts(self, frame: Frame) -> Reading[QuickSlots]:
        labels = self._found
        rows = _lines(y for _, y in labels.values())
        columns = _lines(x for x, _ in labels.values())
        # With one row or column there is no spacing to go by on that axis:
        # borrow the other's, or failing both, a few label sizes.
        biggest = max(max(self._labels[n].rgba.shape[:2]) for n in labels)
        span_y = _pitch(rows) or _pitch(columns) or 3 * biggest
        span_x = _pitch(columns) or _pitch(rows) or 3 * biggest

        cells = {
            (_line(rows, y), _line(columns, x)): name for name, (x, y) in labels.items()
        }
        digit_width = max(d.rgba.shape[1] for d in self._digits.values())
        left = columns[0] - digit_width
        region = (
            left,
            rows[0],
            columns[-1] + span_x - left,
            rows[-1] + span_y - rows[0],
        )
        counts: dict[str, int] = {}
        for run in self._runs(frame.pixels, region):
            if any(abs(run.top - line) < SAME_LINE for line in rows):
                continue  # beside a label, where a cooldown number is drawn
            row = _line_at_or_before(rows, run.top)
            column = _line_at_or_before(columns, run.centre)
            if (
                row is None
                or column is None
                or run.top - rows[row] >= span_y
                or run.centre - columns[column] >= span_x
                or (row, column) not in cells
                or cells[(row, column)] in counts
            ):
                return Reading.unsure(
                    frame.captured_at,
                    f"a count of {run.value} at ({run.centre}, {run.top}) "
                    "belongs to no slot clearly",
                )
            counts[cells[(row, column)]] = run.value

        slots = sorted(
            (
                Slot(
                    _line(rows, y) + 1,
                    _line(columns, x) + 1,
                    name,
                    counts.get(name),
                    x,
                    y,
                )
                for name, (x, y) in labels.items()
            ),
            key=lambda s: (s.row, s.column),
        )
        return Reading.read(QuickSlots(tuple(slots)), frame.captured_at)

    def _runs(
        self, pixels: np.ndarray, region: tuple[int, int, int, int]
    ) -> list[_Run]:
        """Every run of digits in `region`, larger digits winning over smaller
        ones they overlap, like `botting.screen.read_glyphs`."""
        candidates: list[tuple[int, int, int, int, int, str]] = []
        for digit, sprite in self._digits.items():
            h, w = sprite.rgba.shape[:2]
            area = int((sprite.rgba[:, :, 3] == 255).sum())
            for hit in match(pixels, sprite.rgba, region, self._tolerance):
                candidates.append((area, hit.x, hit.y, w, h, digit))
        candidates.sort(key=lambda c: (-c[0], c[1]))
        accepted: list[tuple[int, int, int, int, str]] = []
        for _, x, y, w, h, digit in candidates:
            if any(
                x < ax + aw and ax < x + w and y < ay + ah and ay < y + h
                for ax, ay, aw, ah, _ in accepted
            ):
                continue
            accepted.append((x, y, w, h, digit))
        accepted.sort(key=lambda a: (a[1], a[0]))

        runs: list[list[tuple[int, int, int, int, str]]] = []
        for item in accepted:
            x, y = item[0], item[1]
            if runs:
                px, py, pw, _, _ = runs[-1][-1]
                if y == py and 0 <= x - (px + pw) <= RUN_GAP:
                    runs[-1].append(item)
                    continue
            runs.append([item])
        return [
            _Run(
                top=run[0][1],
                centre=(run[0][0] + run[-1][0] + run[-1][2]) // 2,
                value=int("".join(item[4] for item in run)),
            )
            for run in runs
        ]


def _pack(pixels: np.ndarray) -> np.ndarray:
    """Each BGR pixel as one integer, `b << 16 | g << 8 | r`, so that a colour
    is compared across the frame in one pass."""
    wide = pixels.astype(np.uint32)
    return (wide[:, :, 0] << 16) | (wide[:, :, 1] << 8) | wide[:, :, 2]


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _lines(values: Iterable[int]) -> list[int]:
    """The distinct rows or columns in `values`: the smallest of each group of
    values less than `SAME_LINE` from the group's first, ascending."""
    found: list[int] = []
    for value in sorted(values):
        if not found or value - found[-1] >= SAME_LINE:
            found.append(value)
    return found


def _line_at_or_before(lines: list[int], value: int) -> int | None:
    found = [i for i, line in enumerate(lines) if line <= value]
    return found[-1] if found else None


def _line(lines: list[int], value: int) -> int:
    index = _line_at_or_before(lines, value)
    assert index is not None
    return index


def _pitch(lines: list[int]) -> int | None:
    """The smallest distance between neighbouring rows or columns."""
    gaps = [b - a for a, b in pairwise(lines)]
    return min(gaps) if gaps else None
