"""
Which map the minimap shows, from the banner's title and the map's own
`miniMap/canvas` (#387, epic #302 Part 2 D2). Run once at start, never per
cycle: matching every map's canvas takes most of a second.

**How it decides.** The banner's title (`MinimapTitleReader`) picks the
candidates, the maps the catalogue calls that; a canvas match confirms one: its
canvas drawn in the map area, as `MinimapReader.is_expected_map` counts it
(`MATCHED_SHARE`). `UNSURE` when they disagree (no candidate's canvas is
drawn), or when several candidates' canvases are, which only maps sharing a
canvas can do.

**Without a readable title** (the look without the banner, or a letter not yet
harvested), the canvas match alone decides, over every map's canvas, as the
minimap POC's `--map auto` does: a cheap sampled score of each, then a full
match of the best few. It decides only when the canvas matched belongs to a
single map (spec R-D4); maps sharing a canvas, or two canvases that both match,
are `UNSURE`.

`UNSURE` too when the minimap is minimised, which shows no map; any other
status is the minimap's.

Everything about the maps comes from `game_data` (`MapCanvases.load`).
"""

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from botting.screen import Frame, Reading
from game_data.catalogue import Catalogue
from game_data.config import STORE
from game_data.sprites import Sprite, SpriteNotFound, Sprites

from .minimap import (
    MATCHED_SHARE,
    CanvasMatch,
    MinimapReader,
    OpaquePixels,
    match_canvas,
    minimap_canvas_path,
)
from .minimap_title import MinimapTitleReader

MIN_VISIBLE = 80
"""Fewer of a canvas's opaque pixels than this in the map area can't place it:
a few pixels can be drawn exactly by chance (the minimap POC's threshold)."""

SCREEN_SAMPLE = 60
"""How many of each canvas's opaque pixels the cheap score over every map
compares at each placement."""

SHORTLIST = 5
"""How many of the best cheap scores get a full match."""


@dataclass(frozen=True, slots=True)
class MapCanvas:
    """
    One map's minimap canvas.

    :ivar title: The map's name as the catalogue spells it, `street: map name`.
    :ivar same: A digest of the canvas's pixels: maps with the same one share
        their canvas, so no canvas match can tell them apart.
    """

    map_id: int
    title: str
    canvas: Sprite
    opaque: OpaquePixels
    same: str

    @classmethod
    def of(cls, map_id: int, title: str, canvas: Sprite) -> MapCanvas:
        digest = hashlib.sha256(canvas.rgba.tobytes())
        digest.update(repr(canvas.rgba.shape).encode())
        return cls(map_id, title, canvas, OpaquePixels.of(canvas), digest.hexdigest())


class MapCanvases:
    """Every map's minimap canvas, by map id."""

    def __init__(self, maps: Iterable[MapCanvas]) -> None:
        self._maps: dict[int, MapCanvas] = {m.map_id: m for m in maps}
        self._titled: dict[str, list[MapCanvas]] = {}
        self._same: dict[str, list[int]] = {}
        for m in self._maps.values():
            self._titled.setdefault(m.title, []).append(m)
            self._same.setdefault(m.same, []).append(m.map_id)

    @classmethod
    def load(cls, root: Path = STORE) -> MapCanvases:
        """
        Every map of the store's latest extraction that has a name and a
        minimap canvas with an opaque pixel.

        :raises game_data.catalogue.CatalogueError: The store has no catalogue.
        """
        maps: list[MapCanvas] = []
        with Catalogue.latest(root) as catalogue, Sprites.latest(root) as sprites:
            for map_id in catalogue.ids("map"):
                data = catalogue.map(map_id)
                if data.minimap is None or not data.name:
                    continue
                try:
                    canvas = sprites.canvas(minimap_canvas_path(map_id))
                except SpriteNotFound:
                    continue
                if not (canvas.rgba[:, :, 3] == 255).any():
                    continue
                title = f"{data.street}: {data.name}" if data.street else data.name
                maps.append(MapCanvas.of(map_id, title, canvas))
        return cls(maps)

    def __getitem__(self, map_id: int) -> MapCanvas:
        return self._maps[map_id]

    def __iter__(self) -> Iterator[MapCanvas]:
        return iter(self._maps.values())

    def __len__(self) -> int:
        return len(self._maps)

    @property
    def titles(self) -> frozenset[str]:
        return frozenset(self._titled)

    def titled(self, title: str) -> tuple[MapCanvas, ...]:
        """The maps the catalogue calls `title`."""
        return tuple(self._titled.get(title, ()))

    def sharing(self, map_id: int) -> tuple[int, ...]:
        """The maps whose canvas is `map_id`'s, itself included."""
        return tuple(self._same[self._maps[map_id].same])

    def labelled(self, map_ids: Iterable[int]) -> str:
        return ", ".join(f"{self._maps[i].title} ({i})" for i in map_ids)


class MapIdentifier:
    """Tells which map the minimap shows. Built once at start."""

    def __init__(
        self,
        minimap: MinimapReader,
        title: MinimapTitleReader,
        canvases: MapCanvases,
    ) -> None:
        self._minimap = minimap
        self._title = title
        self._canvases = canvases

    def identify(self, frame: Frame) -> Reading[int]:
        """The map id of the map the minimap in `frame` shows."""
        at = frame.captured_at
        minimap = self._minimap.read(frame)
        view = minimap.value
        if view is None:
            return Reading(None, minimap.status, minimap.frame_time, minimap.detail)
        area = view.map_area
        if area is None:
            return Reading.unsure(at, "the minimap is minimised")
        haystack = frame.pixels[area.top : area.bottom, area.left : area.right]
        title = self._title.read_view(frame, view)
        if title.value is not None:
            return self._confirm(haystack, title.value, at)
        return self._by_canvas(haystack, f"no title ({title.detail})", at)

    def _confirm(self, haystack: np.ndarray, title: str, at: float) -> Reading[int]:
        """The one map called `title` whose canvas is drawn in `haystack`."""
        drawn = [
            m.map_id
            for m in self._canvases.titled(title)
            if _drawn(match_canvas(haystack, m.opaque))
        ]
        if len(drawn) == 1:
            return Reading.read(drawn[0], at, f"titled {title!r}, its minimap drawn")
        if not drawn:
            return Reading.unsure(
                at, f"titled {title!r}, but no map called that has its minimap drawn"
            )
        return Reading.unsure(
            at,
            f"titled {title!r}, and these maps' minimaps are all drawn: "
            + self._canvases.labelled(drawn),
        )

    def _by_canvas(self, haystack: np.ndarray, why: str, at: float) -> Reading[int]:
        """The one map whose canvas is drawn in `haystack`, among every map."""
        scored: list[tuple[float, int]] = []
        for m in self._canvases:
            cheap = match_canvas(haystack, m.opaque, SCREEN_SAMPLE)
            if cheap is not None and cheap.visible >= MIN_VISIBLE:
                scored.append((cheap.share, m.map_id))
        scored.sort(reverse=True)
        drawn = [
            map_id
            for _, map_id in scored[:SHORTLIST]
            if _drawn(match_canvas(haystack, self._canvases[map_id].opaque))
        ]
        if not drawn:
            return Reading.unsure(at, f"{why}; no map's minimap is drawn")
        same = {self._canvases[map_id].same for map_id in drawn}
        if len(same) > 1:
            return Reading.unsure(
                at,
                f"{why}; several maps' minimaps are drawn: "
                + self._canvases.labelled(drawn),
            )
        sharing = self._canvases.sharing(drawn[0])
        if len(sharing) > 1:
            return Reading.unsure(
                at,
                f"{why}; these maps share the minimap drawn: "
                + self._canvases.labelled(sharing),
            )
        return Reading.read(drawn[0], at, f"{why}; its minimap is the only one drawn")


def _drawn(match: CanvasMatch | None) -> bool:
    return (
        match is not None
        and match.visible >= MIN_VISIBLE
        and match.share >= MATCHED_SHARE
    )
