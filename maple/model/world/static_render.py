"""
The static-layer render: what of a map looks the same in every frame, drawn
once from `game_data` and cached on disk per extraction.

It is `game_data.render.render_map` of the map's tiles and objects with one
frame, and of its backgrounds fixed to the map (`rx` and `ry` at
`STORED_AT_RX`), opaque, of a type that doesn't scroll (below 4). Animated
objects, and fixed backgrounds that scroll or are translucent, aren't drawn,
and every pixel they could cover, grown by `MOVING_MARGIN`, is made
transparent, so a reader matching the render never trusts a pixel that
changes. Backgrounds that move with the camera aren't drawn either. This is
the world tracking POC's render (`toolkit/poc_tracking/world_tracker.py`).

Pixel `(0, 0)` is the VR bounds' top left: virtual `(x, y)` is pixel
`(x - vr.left, y - vr.top)`.

The cache is `data/map_render/<build>/<map id>.png` (gitignored, like all of
`data/`), RGBA. It is rebuilt when missing, and a new extraction is a new
folder, so a render never outlives the game data it was drawn from.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import cv2
import numpy as np

from game_data.archive import Pixels
from game_data.catalogue import Catalogue, MapLayer
from game_data.config import STORE
from game_data.render import STORED_AT_RX, Images, render_map

REPO = Path(__file__).resolve().parents[3]
MAP_RENDERS: Final = REPO / "data" / "map_render"
"""Where static renders are cached, one folder per extraction."""

MOVING_MARGIN: Final = 4
"""Pixels around what moves that are made transparent too, on every side."""

SCROLLING_TYPES: Final = 4
"""Background types from this one up scroll over time."""


def is_static(item: MapLayer) -> bool:
    """Drawn the same in every frame, wherever the camera is."""
    if item.background is not None:
        back = item.background
        return _fixed(item) and back.type < SCROLLING_TYPES and back.a == 255
    return len(item.frames) <= 1


def is_moving(item: MapLayer) -> bool:
    """Drawn in the map's frame, but not the same from one frame to the next."""
    if item.background is not None:
        return _fixed(item) and not is_static(item)
    return len(item.frames) > 1


def _fixed(item: MapLayer) -> bool:
    back = item.background
    return back is not None and back.rx == STORED_AT_RX and back.ry == STORED_AT_RX


def draw_static(cat: Catalogue, map_id: int) -> Pixels:
    """The map's static render, RGBA, drawn now (see the module)."""
    images = Images(cat.store.images)
    rgba = render_map(cat, map_id, images=images, keep=is_static)
    moving = render_map(cat, map_id, images=images, keep=is_moving)
    side = 2 * MOVING_MARGIN + 1
    covered = cv2.dilate(
        (moving[..., 3] > 0).astype(np.uint8), np.ones((side, side), np.uint8)
    )
    rgba[covered > 0, 3] = 0
    return rgba


@dataclass(frozen=True, slots=True)
class StaticRender:
    """
    One map's static render, in one extraction, cached on disk.

    :ivar build: The extraction's build id.
    :ivar map_id: The map.
    :ivar root: The game data store the extraction is in.
    :ivar cache: The folder renders are cached under.
    """

    build: str
    map_id: int
    root: Path = STORE
    cache: Path = MAP_RENDERS

    @property
    def path(self) -> Path:
        """Where it is cached."""
        return self.cache / self.build / f"{self.map_id}.png"

    def pixels(self) -> Pixels:
        """
        Its pixels, `(height, width, 4)` RGBA: read from the cache, or drawn
        and cached when missing. Each call reads the file, so hold on to them.

        :raises CatalogueError: The store no longer has the extraction, and
            the render isn't cached.
        """
        cached = self._read()
        if cached is not None:
            return cached
        with Catalogue.open(self.build, self.root) as cat:
            rgba = draw_static(cat, self.map_id)
        self._write(rgba)
        return rgba

    def _read(self) -> Pixels | None:
        if not self.path.is_file():
            return None
        encoded = np.frombuffer(self.path.read_bytes(), np.uint8)
        bgra = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if bgra is None or bgra.ndim != 3 or bgra.shape[2] != 4:
            return None
        return np.asarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA), dtype=np.uint8)

    def _write(self, rgba: Pixels) -> None:
        ok, encoded = cv2.imencode(".png", cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
        if not ok:
            raise OSError(f"the static render of map {self.map_id} didn't encode")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        partial = self.path.with_suffix(f".{os.getpid()}.part")
        partial.write_bytes(encoded.tobytes())
        partial.replace(self.path)
