"""
The minimap: found by its own frame sprites, then the markers read inside it.

**Its three looks.** `UI/MiniMap.img` draws the minimap one of three ways:

- `MaxMap`: expanded, with the map-name banner. A nine-piece frame: the
  corners `nw`, `ne`, `sw`, `se`, edges stretched between them, and a
  transparent centre the map is drawn in. `nw` is as tall as the title bar and
  the banner (72 px).
- `MinMap`: expanded without the banner. The same frame, with a top band only
  as tall as the title bar (29 px).
- `Min`: minimised, the title bar alone: `w`, then `c` stretched, then `e`.

Every piece has its origin at `(0, 0)`, so a piece's position is its top-left
corner.

**Locating an expanded frame.** The anchor is `nw`. Its fixed parts are the
first column of the top edge (`n`, drawn right after `nw`) and the first row of
the left edge (`w`, drawn right below it): their positions follow from `nw`'s
size, whatever the map. `ne` and `sw` sit as far from `nw` as the map is wide
and tall, so they are searched for along `nw`'s row and column; `se` must then
be where both put it. Their offsets are remembered and re-checked first, like
the anchor. The **map area** is the frame's inside: from `nw`'s bottom-right
corner to `ne`'s left edge and `sw`'s top edge. The minimised bar is found the
same way, `w` as anchor, `c` right after it, and `e` along their row.

The look found last is tried first, so a minimap that stays put costs one small
match per piece.

**Markers.** `Map/MapHelper.img/minimap/user` is drawn with its origin on the
character, so `self_position` is where that origin lands, in minimap pixels
from the map area's top-left. The other markers there are given by their
sprite's centre: several have their origin at `(0, 0)`. A marker drawn partly
outside the map area, or partly under another marker, isn't found. Seen on
frame set v2: an NPC's marker is drawn about 14 px above the NPC's own point
in the map data, so a marker's position isn't where the thing stands.

**What the map area shows.** The map's own `miniMap/canvas` is drawn 1:1, but
the map area is a window on it: a canvas narrower than the frame is centred,
with bands either side, and one taller than the map area scrolls with the
character (seen on frame set v2: Damp Forest's 92x158 canvas in a 130x112 area,
Ellinia's 171x318 in a 171x112 one). So a position on the map area is a
position on the canvas only where the canvas isn't scrolled: see #311.

**The expected map.** `is_expected_map` finds where the map's canvas lies in
the map area, as the window above allows, and counts the share of its visible
opaque pixels drawn exactly there. Markers are drawn over it, so not every one
is asked for.
"""

import enum
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

import numpy as np

from botting.screen import Frame, Reading, match, match_best
from botting.utilities import Box
from game_data.sprites import Sprite

from .locator import FrameCheck, Locator, Part, unreadable
from .sprites import Declaration, Profile, ReaderSprites

_MINIMAP_IMG = "UI/MiniMap.img"


@dataclass(frozen=True, slots=True)
class FrameLook:
    """The pieces of one look of the expanded minimap's frame."""

    nw: str
    n: str
    ne: str
    w: str
    sw: str
    se: str

    @classmethod
    def under(cls, node: str) -> FrameLook:
        return cls(*(f"{node}/{piece}" for piece in ("nw", "n", "ne", "w", "sw", "se")))

    @property
    def paths(self) -> tuple[str, ...]:
        return (self.nw, self.n, self.ne, self.w, self.sw, self.se)


WITH_BANNER = FrameLook.under(f"{_MINIMAP_IMG}/MaxMap")
"""Expanded, with the map-name banner under the title bar."""
WITHOUT_BANNER = FrameLook.under(f"{_MINIMAP_IMG}/MinMap")
"""Expanded, without the banner."""

NW, N, NE, W, SW, SE = WITH_BANNER.paths

MIN_W = f"{_MINIMAP_IMG}/Min/w"
MIN_E = f"{_MINIMAP_IMG}/Min/e"

_MAP_HELPER = "Map/MapHelper.img/minimap"
USER = f"{_MAP_HELPER}/user"

MARKER_KINDS = (
    "another",
    "friend",
    "party",
    "partymaster",
    "guild",
    "guildmaster",
    "npc",
    "trunk",
    "portal",
)
"""The `Map/MapHelper.img/minimap` markers `MinimapView.markers` reports, by
their node name. `another` is another player; `trunk` is the storage keeper.
Frame set v2 shows `another`, `npc` and `trunk`; the others aren't seen yet."""

FRAME_PARTS = (*WITH_BANNER.paths, *WITHOUT_BANNER.paths, MIN_W, MIN_E)

MATCHED_SHARE = 0.6
"""At least this share of the map canvas's visible opaque pixels drawn exactly
reads as the expected map. On frame set v2, a map's own canvas is drawn at 74%
to 98% (markers cover the rest), and the other map's at 1% at most."""
DIFFERENT_SHARE = 0.3
"""At most this share reads as another map; in between is `UNSURE`."""


def minimap_canvas_path(map_id: int) -> str:
    """The map's own minimap canvas, such as
    `Map/Map/Map1/100000000.img/miniMap/canvas` for map 100000000."""
    return f"Map/Map/Map{map_id // 100_000_000}/{map_id:09d}.img/miniMap/canvas"


def marker_path(kind: str) -> str:
    return f"{_MAP_HELPER}/{kind}"


def _canvases(profile: Profile) -> tuple[str, ...]:
    expected = () if profile.map_id is None else (minimap_canvas_path(profile.map_id),)
    markers = tuple(marker_path(kind) for kind in MARKER_KINDS)
    return (*FRAME_PARTS, USER, *markers, *expected)


MINIMAP = Declaration("minimap", canvases=_canvases)
"""The frame's three looks, the markers, and the profile's map canvas when its
map file names its `map_id`."""


class MinimapState(enum.Enum):
    EXPANDED = "expanded"
    MINIMISED = "minimised"
    ABSENT = "absent"


type Markers = Mapping[str, tuple[tuple[int, int], ...]]


@dataclass(frozen=True, slots=True)
class MinimapView:
    """
    The minimap, as read.

    :ivar state: `EXPANDED`, with or without the banner, or `MINIMISED`.
    :ivar map_area: Where the map is drawn, in client pixels; `None` when
        minimised.
    :ivar bounds: The whole minimap, frame included, in client pixels: the
        title bar alone when minimised.
    :ivar self_position: The character's position, in minimap pixels from the
        map area's top-left, or `None` when its marker isn't found there
        (covered by another marker or the cursor) or the minimap is minimised.
    :ivar markers: The other markers found, by kind (`MARKER_KINDS`), each as
        positions in the unit of `self_position`. Empty when minimised.
    """

    state: MinimapState
    map_area: Box | None
    bounds: Box
    self_position: tuple[int, int] | None
    markers: Markers = field(default_factory=dict[str, tuple[tuple[int, int], ...]])


class MinimapReader:
    """
    Reads the minimap. One per bot, sharing its `FrameCheck`; it remembers where
    the minimap was, and in which look, and searches again only when it no
    longer matches there.
    """

    def __init__(
        self, sprites: ReaderSprites, frame_check: FrameCheck, tolerance: float = 0.5
    ) -> None:
        self._sprites = sprites
        self._frame_check = frame_check
        self._tolerance = tolerance
        self._user = sprites.canvas(USER)
        self._markers = {
            kind: sprites.canvas(marker_path(kind)) for kind in MARKER_KINDS
        }
        self._looks: tuple[_Expanded | _Minimised, ...] = (
            _Expanded(sprites, WITH_BANNER, tolerance),
            _Expanded(sprites, WITHOUT_BANNER, tolerance),
            _Minimised(sprites, tolerance),
        )
        self._last = 0

    @property
    def searches(self) -> int:
        """How many times a look had to be searched for across the frame,
        rather than found where it was last time."""
        return sum(look.locator.searches for look in self._looks)

    def read(self, frame: Frame) -> Reading[MinimapView]:
        """The minimap in `frame`. Never raises because of what is on screen."""
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        covered: Reading[MinimapView] | None = None
        for index, look in self._in_order():
            located = look.locator.locate(frame)
            not_whole = unreadable(located, frame)
            if not_whole is not None:
                # A look partly found may be another look's pieces: try them all
                # before saying it is covered.
                if located is not None and covered is None:
                    covered = not_whole
                continue
            assert located is not None
            placed = look.place(frame.pixels, located.point)
            if isinstance(placed, str):
                covered = covered or Reading.covered(frame.captured_at, placed)
                continue
            self._last = index
            return Reading.read(self._view(frame.pixels, placed), frame.captured_at)
        return covered or Reading.absent(frame.captured_at, "not found")

    def is_expected_map(self, frame: Frame, map_id: int) -> Reading[bool]:
        """
        Whether the map drawn in the minimap is `map_id`'s own `miniMap/canvas`.

        `READ` with `False` when too few of the canvas's visible opaque pixels
        are drawn where it fits best; `UNSURE` when the share is between
        `DIFFERENT_SHARE` and `MATCHED_SHARE`, or the minimap is minimised. Any
        other status is the minimap's.

        :raises KeyError: The bot's profile didn't name `map_id`, so its canvas
            wasn't loaded.
        """
        canvas = self._sprites.canvas(minimap_canvas_path(map_id))
        minimap = self.read(frame)
        if minimap.value is None:
            return Reading(None, minimap.status, minimap.frame_time, minimap.detail)
        area = minimap.value.map_area
        if area is None:
            return Reading.unsure(frame.captured_at, "the minimap is minimised")
        haystack = frame.pixels[area.top : area.bottom, area.left : area.right]
        share = _drawn_share(haystack, canvas)
        detail = f"{share:.0%} of map {map_id}'s minimap drawn"
        if share >= MATCHED_SHARE:
            return Reading.read(True, frame.captured_at, detail)
        if share <= DIFFERENT_SHARE:
            return Reading.read(False, frame.captured_at, detail)
        return Reading.unsure(frame.captured_at, detail)

    def _in_order(self) -> Iterator[tuple[int, _Expanded | _Minimised]]:
        yield self._last, self._looks[self._last]
        for index, look in enumerate(self._looks):
            if index != self._last:
                yield index, look

    def _view(self, pixels: np.ndarray, placed: _Placed) -> MinimapView:
        area = placed.map_area
        if area is None:
            return MinimapView(MinimapState.MINIMISED, None, placed.bounds, None, {})
        user = _find(pixels, self._user, area, self._tolerance)
        markers = {
            kind: found
            for kind, sprite in self._markers.items()
            if (found := _find(pixels, sprite, area, self._tolerance, every=True))
        }
        return MinimapView(
            MinimapState.EXPANDED,
            area,
            placed.bounds,
            user[0] if user else None,
            markers,
        )


@dataclass(frozen=True, slots=True)
class _Placed:
    bounds: Box
    map_area: Box | None


class _Expanded:
    """One look of the expanded frame: `nw` and its fixed parts, then the
    corners found along its row and column."""

    def __init__(
        self, sprites: ReaderSprites, look: FrameLook, tolerance: float
    ) -> None:
        self._tolerance = tolerance
        nw = sprites.canvas(look.nw)
        self._ne = sprites.canvas(look.ne)
        self._sw = sprites.canvas(look.sw)
        self._se = sprites.canvas(look.se)
        self._look = look
        self._border, self._band = _size(nw)
        self.locator = Locator(
            Part(nw),
            (
                Part(sprites.canvas(look.n), (self._border, 0)),
                Part(sprites.canvas(look.w), (0, self._band)),
            ),
            tolerance,
        )
        # Where `ne` and `sw` were last found, relative to the frame's point.
        self._ne_at: tuple[int, int] | None = None
        self._sw_at: tuple[int, int] | None = None

    def place(self, pixels: np.ndarray, point: tuple[int, int]) -> _Placed | str:
        """The frame whose `nw` is at `point`, or what wasn't where expected."""
        x, y = point
        ne = _along(
            pixels, self._ne, self._ne_at, point, (self._border, 0), self._tolerance
        )
        sw = _along(
            pixels, self._sw, self._sw_at, point, (0, self._band), self._tolerance
        )
        if ne is None or sw is None:
            missing = [
                p for p, at in ((self._look.ne, ne), (self._look.sw, sw)) if at is None
            ]
            return "not where expected: " + ", ".join(missing)
        self._ne_at = (ne[0] - x, ne[1] - y)
        self._sw_at = (sw[0] - x, sw[1] - y)
        if not _matches(pixels, self._se, (ne[0], sw[1]), self._tolerance):
            return f"not where expected: {self._look.se}"
        se_w, se_h = _size(self._se)
        return _Placed(
            bounds=Box(left=x, right=ne[0] + se_w, top=y, bottom=sw[1] + se_h),
            map_area=Box(
                left=x + self._border, right=ne[0], top=y + self._band, bottom=sw[1]
            ),
        )


class _Minimised:
    """
    The title bar alone: `w`, then `e` along its row. `c` isn't a fixed part:
    the map's name is drawn over it from right after `w` (frame f037).
    """

    def __init__(self, sprites: ReaderSprites, tolerance: float) -> None:
        self._tolerance = tolerance
        w = sprites.canvas(MIN_W)
        self._e = sprites.canvas(MIN_E)
        self._w_width, self._height = _size(w)
        self.locator = Locator(Part(w), (), tolerance)
        self._e_at: tuple[int, int] | None = None

    def place(self, pixels: np.ndarray, point: tuple[int, int]) -> _Placed | str:
        x, y = point
        e = _along(
            pixels, self._e, self._e_at, point, (self._w_width, 0), self._tolerance
        )
        if e is None:
            return f"not where expected: {MIN_E}"
        self._e_at = (e[0] - x, e[1] - y)
        e_w, _ = _size(self._e)
        return _Placed(
            Box(left=x, right=e[0] + e_w, top=y, bottom=y + self._height), None
        )


def _along(
    pixels: np.ndarray,
    sprite: Sprite,
    remembered: tuple[int, int] | None,
    point: tuple[int, int],
    start: tuple[int, int],
    tolerance: float,
) -> tuple[int, int] | None:
    """
    Where `sprite` is, on `point`'s row (`start` is `(dx, 0)`) or column
    (`(0, dy)`), from `start` on: first where it was last time, then the
    nearest one to `point`.
    """
    x, y = point
    if remembered is not None:
        at = (x + remembered[0], y + remembered[1])
        if _matches(pixels, sprite, at, tolerance):
            return at
    w, h = _size(sprite)
    dx, dy = start
    if dy == 0:
        region = (x + dx, y, pixels.shape[1] - x - dx, h)
    else:
        region = (x, y + dy, w, pixels.shape[0] - y - dy)
    hits = match(pixels, sprite.rgba, region, tolerance)
    if not hits:
        return None
    nearest = min(hits, key=lambda hit: hit.x + hit.y)
    return nearest.x, nearest.y


def _matches(
    pixels: np.ndarray, sprite: Sprite, at: tuple[int, int], tolerance: float
) -> bool:
    w, h = _size(sprite)
    hits = match(pixels, sprite.rgba, (at[0], at[1], w, h), tolerance)
    return any((hit.x, hit.y) == at for hit in hits)


def _find(
    pixels: np.ndarray,
    sprite: Sprite,
    area: Box,
    tolerance: float,
    every: bool = False,
) -> tuple[tuple[int, int], ...]:
    """
    Where `sprite` is drawn in `area`, in minimap pixels from its top-left:
    the best match, or `every` match apart from the others. The player's
    marker is placed by its origin; `every` other marker by its centre, since
    several (`npc`, `trunk`, `portal`) have their origin at `(0, 0)`, and the
    round ones have it at their centre.

    A marker is centred on what it marks, so near an edge of the map it pokes
    out of the map area: a margin of its size around it is searched.
    """
    w, h = _size(sprite)
    region = (area.left - w, area.top - h, area.width + 2 * w, area.height + 2 * h)
    if every:
        hits = sorted(
            match(pixels, sprite.rgba, region, tolerance), key=lambda h: h.error
        )
    else:
        best = match_best(pixels, sprite.rgba, region, tolerance)
        hits = [best] if best is not None else []
    kept: list[tuple[int, int]] = []
    for hit in hits:
        # Neighbouring positions of one marker can both match: keep the best.
        if all(abs(hit.x - x) >= w // 2 or abs(hit.y - y) >= h // 2 for x, y in kept):
            kept.append((hit.x, hit.y))
    ox, oy = (w // 2, h // 2) if every else sprite.origin
    return tuple(sorted((x + ox - area.left, y + oy - area.top) for x, y in kept))


def _size(sprite: Sprite) -> tuple[int, int]:
    h, w = sprite.rgba.shape[:2]
    return w, h


SAMPLE = 400
"""How many of the canvas's opaque pixels, evenly spread, are compared at every
placement while looking for where it fits; the share is then counted on all
of them, at the best placement."""


def _offsets(area: int, length: int) -> np.ndarray:
    """The canvas's possible offsets from the map area along one axis: inside
    it where it fits, as a window on it where it is longer (it scrolls)."""
    if length <= area:
        return np.arange(0, area - length + 1)
    return np.arange(area - length, 1)


def _drawn_share(haystack: np.ndarray, canvas: Sprite) -> float:
    """
    The share of `canvas`'s visible opaque pixels drawn exactly in `haystack`,
    where most of them are: along an axis the canvas fits in, anywhere inside;
    along one it is longer, as a window on it. `0.0` when nothing opaque shows.

    Placements are ranked by how many pixels are drawn exactly, not by a
    squared error, which the markers drawn over the map would outweigh, nor by
    the share, which a window showing few opaque pixels can fill by chance.
    """
    area_h, area_w = haystack.shape[:2]
    rgba = canvas.rgba
    ys, xs = np.nonzero(rgba[:, :, 3] == 255)
    if len(ys) == 0:
        return 0.0
    colours = rgba[ys, xs, 2::-1]
    step = max(1, len(ys) // SAMPLE)
    sy, sx, sc = ys[::step], xs[::step], colours[::step]
    off_y = _offsets(area_h, rgba.shape[0])
    off_x = _offsets(area_w, rgba.shape[1])
    counts = np.zeros((len(off_y), len(off_x)), dtype=np.int64)
    for i, dy in enumerate(off_y):
        py = sy + dy
        px = sx[None, :] + off_x[:, None]
        inside = ((py >= 0) & (py < area_h))[None, :] & (px >= 0) & (px < area_w)
        got = haystack[np.clip(py, 0, area_h - 1)[None, :], np.clip(px, 0, area_w - 1)]
        drawn = np.all(got == sc[None, :, :], axis=2) & inside
        counts[i] = drawn.sum(axis=1)
    i, j = np.unravel_index(int(np.argmax(counts)), counts.shape)
    py, px = ys + off_y[i], xs + off_x[j]
    inside = (py >= 0) & (py < area_h) & (px >= 0) & (px < area_w)
    if not inside.any():
        return 0.0
    got = haystack[py[inside], px[inside]]
    return float(np.all(got == colours[inside], axis=1).mean())
