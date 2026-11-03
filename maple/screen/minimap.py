"""
The minimap: found by its own frame sprites, then the character's marker read
inside it.

**Locating.** The expanded minimap is drawn as a nine-piece frame,
`UI/MiniMap.img/MaxMap`: the corners `nw`, `ne`, `sw`, `se`, edges stretched
between them, and a transparent centre the map is drawn in. Every piece has its
origin at `(0, 0)`, so a piece's position is its top-left corner.

- The anchor is `nw`. Its fixed parts are the first column of the top edge
  (`n`, drawn right after `nw`) and the first row of the left edge (`w`, drawn
  right below it): their positions follow from `nw`'s size, whatever the map.
- `ne` and `sw` sit as far from `nw` as the map is wide and tall, so they are
  searched for along `nw`'s row and column; `se` must then be where both put it.
  Their offsets are remembered and re-checked first, like the anchor.
- The **map area** is the frame's inside: from `nw`'s bottom-right corner to
  `ne`'s left edge and `sw`'s top edge.

**Position.** `Map/MapHelper.img/minimap/user` is drawn with its origin on the
character, so `self_position` is where that origin lands, in minimap pixels from
the map area's top-left: the unit `configs/maps/` is recorded in.

**The expected map.** `is_expected_map` compares the map's own
`miniMap/canvas` with the map area's pixels. Markers are drawn over it, so it
counts the share of the canvas's opaque pixels drawn exactly, rather than asking
for every one.

Not built yet, for want of frames of them (#311): the minimised state
(`MinMap`), which reads `ABSENT` until then, and the other markers, which
`MinimapView.markers` leaves `None`.
"""

import enum
from collections.abc import Mapping
from dataclasses import dataclass

import cv2
import numpy as np

from botting.screen import Frame, Reading, match, match_best
from botting.utilities import Box
from game_data.sprites import Sprite

from .locator import FrameCheck, Locator, Part, unreadable
from .sprites import Declaration, Profile, ReaderSprites

_MAX_MAP = "UI/MiniMap.img/MaxMap"
NW = f"{_MAX_MAP}/nw"
N = f"{_MAX_MAP}/n"
NE = f"{_MAX_MAP}/ne"
W = f"{_MAX_MAP}/w"
SW = f"{_MAX_MAP}/sw"
SE = f"{_MAX_MAP}/se"
USER = "Map/MapHelper.img/minimap/user"

FRAME_PARTS = (NW, N, NE, W, SW, SE)

MATCHED_SHARE = 0.9
"""At least this share of the map canvas's opaque pixels drawn exactly reads as
the expected map. Provisional: chosen without frames, to be checked on them."""
DIFFERENT_SHARE = 0.5
"""At most this share reads as another map; in between is `UNSURE`. Provisional,
like `MATCHED_SHARE`."""


def minimap_canvas_path(map_id: int) -> str:
    """The map's own minimap canvas, such as
    `Map/Map/Map1/100000000.img/miniMap/canvas` for map 100000000."""
    return f"Map/Map/Map{map_id // 100_000_000}/{map_id:09d}.img/miniMap/canvas"


def _canvases(profile: Profile) -> tuple[str, ...]:
    expected = () if profile.map_id is None else (minimap_canvas_path(profile.map_id),)
    return (*FRAME_PARTS, USER, *expected)


MINIMAP = Declaration("minimap", canvases=_canvases)
"""The frame, the player marker, and the profile's map canvas when its map file
names its `map_id`."""


class MinimapState(enum.Enum):
    EXPANDED = "expanded"
    MINIMISED = "minimised"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class MinimapView:
    """
    The minimap, as read.

    :ivar state: Only `EXPANDED` is read for now.
    :ivar map_area: Where the map is drawn, in client pixels.
    :ivar bounds: The whole minimap, frame included, in client pixels.
    :ivar self_position: The character's position, in minimap pixels from the
        map area's top-left, or `None` when its marker isn't found there (covered
        by another marker or the cursor).
    :ivar markers: Other players', NPCs' and portals' positions, by kind. `None`:
        not read yet, waiting for frames of them.
    """

    state: MinimapState
    map_area: Box
    bounds: Box
    self_position: tuple[int, int] | None
    markers: Mapping[str, tuple[tuple[int, int], ...]] | None = None


class MinimapReader:
    """
    Reads the minimap. One per bot, sharing its `FrameCheck`; it remembers where
    the minimap was, and searches again only when it no longer matches there.
    """

    def __init__(
        self, sprites: ReaderSprites, frame_check: FrameCheck, tolerance: float = 0.5
    ) -> None:
        self._sprites = sprites
        self._frame_check = frame_check
        self._tolerance = tolerance
        self._nw = sprites.canvas(NW)
        self._ne = sprites.canvas(NE)
        self._sw = sprites.canvas(SW)
        self._se = sprites.canvas(SE)
        self._user = sprites.canvas(USER)
        border, band = _size(self._nw)
        self._border = border
        self._band = band
        self.locator = Locator(
            Part(self._nw),
            (Part(sprites.canvas(N), (border, 0)), Part(sprites.canvas(W), (0, band))),
            tolerance,
        )
        # Where `ne` and `sw` were last found, relative to the frame's point.
        self._ne_at: tuple[int, int] | None = None
        self._sw_at: tuple[int, int] | None = None

    def read(self, frame: Frame) -> Reading[MinimapView]:
        """The minimap in `frame`. Never raises because of what is on screen."""
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        located = self.locator.locate(frame)
        not_whole = unreadable(located, frame)
        if not_whole is not None:
            return not_whole
        assert located is not None
        x, y = located.point
        pixels = frame.pixels
        ne = self._corner(pixels, self._ne, self._ne_at, (x, y), along="row")
        sw = self._corner(pixels, self._sw, self._sw_at, (x, y), along="column")
        missing = [path for path, at in ((NE, ne), (SW, sw)) if at is None]
        if ne is None or sw is None:
            return Reading.covered(
                frame.captured_at, "not where expected: " + ", ".join(missing)
            )
        self._ne_at = (ne[0] - x, ne[1] - y)
        self._sw_at = (sw[0] - x, sw[1] - y)
        if not self._matches(pixels, self._se, (ne[0], sw[1])):
            return Reading.covered(frame.captured_at, f"not where expected: {SE}")

        se_w, se_h = _size(self._se)
        map_area = Box(
            left=x + self._border, right=ne[0], top=y + self._band, bottom=sw[1]
        )
        bounds = Box(left=x, right=ne[0] + se_w, top=y, bottom=sw[1] + se_h)
        view = MinimapView(
            MinimapState.EXPANDED,
            map_area,
            bounds,
            self._self_position(pixels, map_area),
        )
        return Reading.read(view, frame.captured_at)

    def is_expected_map(self, frame: Frame, map_id: int) -> Reading[bool]:
        """
        Whether the map drawn in the minimap is `map_id`'s own `miniMap/canvas`.

        `READ` with `False` when the canvas doesn't fit the map area, or too few
        of its opaque pixels are drawn there; `UNSURE` when the share is between
        `DIFFERENT_SHARE` and `MATCHED_SHARE`. Any other status is the minimap's.

        :raises KeyError: The bot's profile didn't name `map_id`, so its canvas
            wasn't loaded.
        """
        canvas = self._sprites.canvas(minimap_canvas_path(map_id))
        minimap = self.read(frame)
        if minimap.value is None:
            return Reading(None, minimap.status, minimap.frame_time, minimap.detail)
        area = minimap.value.map_area
        haystack = frame.pixels[area.top : area.bottom, area.left : area.right]
        share = _drawn_share(haystack, canvas)
        detail = f"{share:.0%} of map {map_id}'s minimap drawn"
        if share >= MATCHED_SHARE:
            return Reading.read(True, frame.captured_at, detail)
        if share <= DIFFERENT_SHARE:
            return Reading.read(False, frame.captured_at, detail)
        return Reading.unsure(frame.captured_at, detail)

    def _corner(
        self,
        pixels: np.ndarray,
        sprite: Sprite,
        remembered: tuple[int, int] | None,
        point: tuple[int, int],
        along: str,
    ) -> tuple[int, int] | None:
        """Where `sprite` is, on `point`'s row or column: first where it was last
        time, then the nearest one to `point`."""
        x, y = point
        if remembered is not None:
            at = (x + remembered[0], y + remembered[1])
            if self._matches(pixels, sprite, at):
                return at
        w, h = _size(sprite)
        if along == "row":
            start = x + self._border
            region = (start, y, pixels.shape[1] - start, h)
        else:
            start = y + self._band
            region = (x, start, w, pixels.shape[0] - start)
        hits = match(pixels, sprite.rgba, region, self._tolerance)
        if not hits:
            return None
        nearest = min(hits, key=lambda hit: hit.x + hit.y)
        return nearest.x, nearest.y

    def _matches(self, pixels: np.ndarray, sprite: Sprite, at: tuple[int, int]) -> bool:
        w, h = _size(sprite)
        hits = match(pixels, sprite.rgba, (at[0], at[1], w, h), self._tolerance)
        return any((hit.x, hit.y) == at for hit in hits)

    def _self_position(
        self, pixels: np.ndarray, map_area: Box
    ) -> tuple[int, int] | None:
        # The marker is centred on the character, so near an edge of the map it
        # pokes out of the map area: search a margin of its size around it.
        w, h = _size(self._user)
        region = (
            map_area.left - w,
            map_area.top - h,
            map_area.width + 2 * w,
            map_area.height + 2 * h,
        )
        hit = match_best(pixels, self._user.rgba, region, self._tolerance)
        if hit is None:
            return None
        ox, oy = self._user.origin
        return hit.x + ox - map_area.left, hit.y + oy - map_area.top


def _size(sprite: Sprite) -> tuple[int, int]:
    h, w = sprite.rgba.shape[:2]
    return w, h


def _drawn_share(haystack: np.ndarray, canvas: Sprite) -> float:
    """
    The share of `canvas`'s opaque pixels drawn exactly in `haystack`, where it
    fits best; `0.0` when it doesn't fit at all.
    """
    rgba = canvas.rgba
    mask = rgba[:, :, 3] == 255
    count = int(mask.sum())
    ch, cw = mask.shape
    if count == 0 or haystack.shape[0] < ch or haystack.shape[1] < cw:
        return 0.0
    bgr = np.ascontiguousarray(rgba[:, :, 2::-1])
    x = y = 0
    if haystack.shape[:2] != (ch, cw):
        mask3 = np.repeat(mask[:, :, None], 3, axis=2).astype(np.float32)
        scores = cv2.matchTemplate(
            np.ascontiguousarray(haystack), bgr, cv2.TM_SQDIFF, mask=mask3
        )
        _, _, (x, y), _ = cv2.minMaxLoc(scores)
    patch = haystack[y : y + ch, x : x + cw]
    drawn = np.all(patch[mask] == bgr[mask], axis=1)
    return float(drawn.sum()) / count
