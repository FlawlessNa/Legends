"""
The quick slots: each slot's key label found by its own sprite, then the item
count drawn in the slot read with the client's digit sprites.

**Labels.** Every key's label, `UI/QuickSlot.img/key/<name>`, is its own anchor:
it is searched for on its own, and where it was found is remembered. Once any
were found, later frames re-check just those spots, and a label found earlier
that no longer matches makes the reading `COVERED`. The slot background isn't
an anchor (its alpha is 0 to 39).

**Searching again.** A first search may see a partly covered panel, which would
number the slots wrongly, so the numbering is trusted only once two searches at
least `SEARCH_EVERY` seconds apart find the same labels: until then the reading
is `UNSURE`, and the search repeats.

Once settled, the labels found are kept for good: while one doesn't match where
it was found the reading is `COVERED`, however long that lasts, and it reads
again the moment the label is back. A search (at most every `SEARCH_EVERY`
seconds, while covered) replaces the remembered labels only when the result
cannot renumber a slot: it has a label at every remembered position and numbers
each as before (a key rebound in the slot, a label found that was missed), or it
is a filled grid with at least as many rows and columns (the panel moved). A
covered first row or column never replaces anything, since what's left would be
numbered from the wrong end.

**Known gap.** The number of rows isn't known, so a cover over a whole top row
during both settling searches settles with the remaining rows numbered from 1
(`slot(1)` is then another slot). Nor can a cursor or tooltip over a slot's
count be told from no count drawn, or a shorter one: a hidden count reads
`None` or a smaller number, as `READ`.

**Columns.** The layout is `COLUMNS` slots to a row, so labels found in fewer
columns mean part of the panel isn't visible (a window over it): `COVERED`, and
the numbering is not settled, so the search repeats until a full set of columns
is found and two searches agree. A slot column with no key bound reads `COVERED`
for good.

**Holes.** The grid the labels found make should have a label in every cell.
A cell with none is a slot that is unbound, covered, or shaded by a cooldown, and
a fresh reader can't tell which, nor read a shaded key: the numbering isn't
settled and the reading is `UNSURE`. A reader that settled on a full grid keeps
its keys through a cooldown (`_at`). So a slot with no key bound keeps the reader
`UNSURE`.

**Suspect labels.** A label whose pixels are all drawn by a longer one (`P`, key
25, starts `PgUp` and `PgDn`) can't be told from the longer label shaded by a
cooldown, so a cell that matches only such a label is a hole too, and the reader
is `UNSURE`. A slot bound to one of those keys (`_suspects`) never settles.

**Shaded labels.** A cooldown shades part of a slot's label, so it isn't found
by the exact search. At each cell of the grid the exact matches make, the label
with the most opaque pixels wins among those drawn there, exactly or shaded
(`_fits`): a long label shaded beats a short one wholly drawn. Two
keys can look identical (`0` and `O`); the first in `KEY_NAMES` is reported.

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

A run that starts within `SAME_LINE` of a label's top and right of the label is
beside it, not under it, and isn't a count: it is a cooldown number, which the client draws
with the same digits at the slot's top right while the slot recharges. It is
skipped, and the slot keeps the count drawn below.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from botting.screen import Frame, Reading, match
from game_data.sprites import Sprite

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

MIN_SHARE = 0.25
"""A label already found still counts as drawn when this share of its opaque
pixels is exactly as drawn: the rows of it a cooldown hasn't shaded. Provisional:
chosen on a few frames (f020's `PgUp` has 0.38 of them)."""
MIN_CORRELATION = 0.95
"""How well the brightness of a label's shaded rows must follow the sprite's.
Provisional: chosen on a few frames (the right label scored 1.0, the next best
0.89)."""
MIN_SHADED_PIXELS = 6
"""Fewer opaque pixels than this in a label's shaded rows say nothing."""
_EVEN_SHADE = 12.0

SEARCH_EVERY = 3.0
"""Seconds between searches for labels while the grid isn't settled or a label
has moved. A search takes 1 to 2 s, so it is not done every frame."""

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

    left: int
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
        self._opaque = {
            name: int((label.rgba[:, :, 3] == 255).sum())
            for name, label in self._labels.items()
        }
        self._suspect = _suspects(self._labels)
        self._digits = {d: sprites.canvas(f"{_ITEM_NO}/{d}") for d in DIGITS}
        self._found: dict[str, tuple[int, int]] = {}
        self._settled = False
        self._searched_at: float | None = None
        self.searches = 0
        self._client_size: tuple[int, int] | None = None

    def read(self, frame: Frame) -> Reading[QuickSlots]:
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        pixels = frame.pixels
        if frame.client_size != self._client_size:
            self._client_size = frame.client_size
            self._found = {}
            self._settled = False
            self._searched_at = None
        moved = [
            name for name, at in self._found.items() if not self._at(pixels, name, at)
        ]
        due = (
            self._searched_at is None
            or frame.captured_at - self._searched_at >= SEARCH_EVERY
        )
        if due and (not self._found or not self._settled):
            found = self._search(pixels)
            self._searched_at = frame.captured_at
            self._settled = (
                found == self._found
                and _columns(found) >= COLUMNS
                and not _holes(found)
            )
            self._found = found
            moved = []
        elif due and moved:
            # Settled: a covered label is not a reason to forget it. Take what
            # a search finds only if it keeps every slot's number.
            found = self._search(pixels)
            self._searched_at = frame.captured_at
            if _replaces(self._found, found):
                self._found = found
                moved = []
        if not self._found:
            return Reading.absent(frame.captured_at, "no key label found")
        if moved:
            return Reading.covered(
                frame.captured_at,
                "label not where it was found: " + ", ".join(moved),
            )
        if not self._settled:
            columns = _columns(self._found)
            if columns < COLUMNS:
                return Reading.covered(
                    frame.captured_at,
                    f"labels found in {columns} of the layout's {COLUMNS} columns",
                )
            holes = _holes(self._found)
            why = (
                "no label found for the slot at row "
                f"{holes[0][0] + 1}, column {holes[0][1] + 1}: unbound, shaded "
                "by a cooldown or covered, and which isn't known until it is seen"
                if holes
                else "the labels found must be the same in two searches "
                f"{SEARCH_EVERY:g} s apart"
            )
            return Reading.unsure(
                frame.captured_at, f"slot numbering not settled: {why}"
            )
        return self._counts(frame)

    def _at(self, pixels: np.ndarray, name: str, at: tuple[int, int]) -> bool:
        """
        Whether the label still looks drawn at `at`: `_fits`, or at least
        `MIN_SHARE` of it exactly drawn, since a cooldown shades a label in ways
        `_fits` can't always follow (the shade isn't one constant change) and
        the slot is still the same slot.
        """
        if self._fits(pixels, name, at):
            return True
        rgba = self._labels[name].rgba
        h, w = rgba.shape[:2]
        x, y = at
        if x < 0 or y < 0 or y + h > pixels.shape[0] or x + w > pixels.shape[1]:
            return False
        mask = rgba[:, :, 3] == 255
        drawn = pixels[y : y + h, x : x + w][mask]
        exact = np.all(drawn == rgba[:, :, 2::-1][mask], axis=1)
        return float(exact.mean()) >= MIN_SHARE

    def _fits(self, pixels: np.ndarray, name: str, at: tuple[int, int]) -> bool:
        """
        Whether the label is drawn at `at`: exactly, or with a cooldown's shade
        over its lower (or upper) rows. The shade sweeps across a slot, so the
        rows on one side of a boundary are exact and the rows on the other have
        every pixel changed the same way, which keeps their brightness
        correlated with the sprite's (at least `MIN_CORRELATION`).
        """
        rgba = self._labels[name].rgba
        h, w = rgba.shape[:2]
        x, y = at
        if x < 0 or y < 0 or y + h > pixels.shape[0] or x + w > pixels.shape[1]:
            return False
        mask = rgba[:, :, 3] == 255
        drawn = pixels[y : y + h, x : x + w]
        same = np.all(drawn == rgba[:, :, 2::-1], axis=2) | ~mask
        row_exact = same.all(axis=1)
        if row_exact.all():
            return True
        sprite = rgba[:, :, :3].astype(float).mean(axis=2)
        seen = drawn.astype(float).mean(axis=2)
        for rows in (
            slice(int(np.argmin(row_exact)), h),  # exact above the boundary
            slice(0, h - int(np.argmin(row_exact[::-1]))),  # exact below it
        ):
            shaded = np.zeros_like(mask)
            shaded[rows] = mask[rows]
            if int(shaded.sum()) < MIN_SHADED_PIXELS:
                continue
            ours, theirs = sprite[shaded], seen[shaded]
            if ours.std() < 1e-6:
                # Nothing to correlate with: the rows must be evenly shaded.
                if theirs.std() < _EVEN_SHADE:
                    return True
                continue
            if theirs.std() < 1e-6:
                continue
            if float(np.corrcoef(ours, theirs)[0, 1]) >= MIN_CORRELATION:
                return True
        return False

    def _resolve(
        self, pixels: np.ndarray, found: dict[str, tuple[int, int]]
    ) -> dict[str, tuple[int, int]]:
        """
        Each slot's label, chosen where the exact search found some: a cooldown
        shades part of a label so it isn't found exactly, and a short label can
        match inside a longer one. So at every cell of the grid the found labels
        make, the label drawn there (`_fits`) with the most opaque pixels wins
        (a long label shaded beats a short one wholly drawn: it explains more),
        and a tie between identical-looking labels (`0` and `O`) goes to the
        first in `KEY_NAMES`.
        """
        rows = _lines(y for _, y in found.values())
        columns = _lines(x for x, _ in found.values())
        resolved: dict[str, tuple[int, int]] = {}
        for y in rows:
            for x in columns:
                best: tuple[int, str] | None = None
                for name in self._labels:
                    if not self._fits(pixels, name, (x, y)):
                        continue
                    size = self._opaque[name]
                    if best is None or size > best[0]:
                        best = (size, name)
                if (
                    best is not None
                    and best[1] not in self._suspect
                    and best[1] not in resolved
                ):
                    resolved[best[1]] = (x, y)
        return resolved

    def _search(self, pixels: np.ndarray) -> dict[str, tuple[int, int]]:
        """
        Every slot's label in `pixels`: the exact matches give the grid, and
        `_resolve` picks each slot's label.
        """
        self.searches += 1
        packed = _pack(pixels)
        found: dict[str, tuple[int, int]] = {}
        for name, label in self._labels.items():
            at = self._find(pixels, packed, label.rgba)
            if at is not None:
                found[name] = at

        return self._resolve(pixels, found)

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
            if any(
                abs(run.top - y) < SAME_LINE
                and run.left >= x + self._labels[name].rgba.shape[1]
                for name, (x, y) in labels.items()
            ):
                continue  # right of a label, level with it: a cooldown number
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
                left=run[0][0],
                top=run[0][1],
                centre=(run[0][0] + run[-1][0] + run[-1][2]) // 2,
                value=int("".join(item[4] for item in run)),
            )
            for run in runs
        ]


def _replaces(old: dict[str, tuple[int, int]], new: dict[str, tuple[int, int]]) -> bool:
    """
    Whether the labels `new` found may replace the settled `old`, without
    renumbering any slot or shrinking the grid.
    """
    if not new:
        return False
    before = set(old.values())
    after = set(new.values())

    def numbering(
        positions: set[tuple[int, int]],
    ) -> dict[tuple[int, int], tuple[int, int]]:
        rows = _lines(y for _, y in positions)
        columns = _lines(x for x, _ in positions)
        return {(x, y): (_line(rows, y), _line(columns, x)) for x, y in positions}

    kept = before <= after and all(
        numbering(after)[p] == numbering(before)[p] for p in before
    )
    rows = _lines(y for _, y in after)
    columns = _lines(x for x, _ in after)
    filled = (
        len(after) == len(rows) * len(columns)
        and len(rows) >= len(_lines(y for _, y in before))
        and len(columns) >= len(_lines(x for x, _ in before))
    )
    return kept or filled


def _pack(pixels: np.ndarray) -> np.ndarray:
    """Each BGR pixel as one integer, `b << 16 | g << 8 | r`, so that a colour
    is compared across the frame in one pass."""
    wide = pixels.astype(np.uint32)
    return (wide[:, :, 0] << 16) | (wide[:, :, 1] << 8) | wide[:, :, 2]


def _suspects(labels: dict[str, Sprite]) -> set[str]:
    """
    The labels whose opaque pixels are all drawn, in the same place and colours,
    by a longer label: the `P` (key 25) that starts `PgUp` and `PgDn`, the `I`
    of `Ins`, the `S` of `Shift`. With the longer label shaded by a cooldown,
    only the short one still matches exactly, so it can't be told from the real
    thing.
    """
    suspects: set[str] = set()
    for short, a in labels.items():
        ma = a.rgba[:, :, 3] == 255
        if not ma.any():
            continue
        h, w = ma.shape
        for other, b in labels.items():
            if other == short or b.rgba.shape[0] < h or b.rgba.shape[1] < w:
                continue
            mb = b.rgba[:h, :w, 3] == 255
            if (
                int((b.rgba[:, :, 3] == 255).sum()) > int(ma.sum())
                and bool(mb[ma].all())
                and bool(np.all(a.rgba[:, :, :3][ma] == b.rgba[:h, :w, :3][ma]))
            ):
                suspects.add(short)
                break
    return suspects


def _columns(found: dict[str, tuple[int, int]]) -> int:
    return len(_lines(x for x, _ in found.values()))


def _holes(found: dict[str, tuple[int, int]]) -> list[tuple[int, int]]:
    """The cells of the grid the labels found make that have none, as
    `(row, column)` from 0."""
    rows = _lines(y for _, y in found.values())
    columns = _lines(x for x, _ in found.values())
    filled = {(_line(rows, y), _line(columns, x)) for x, y in found.values()}
    return [
        (r, c)
        for r in range(len(rows))
        for c in range(len(columns))
        if (r, c) not in filled
    ]


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
