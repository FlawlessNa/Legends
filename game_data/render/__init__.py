"""
Map screens: a map drawn whole, in virtual coordinates, from the catalogue and
the image store. It never reads the client.

The public API:

- `render_map(cat, map, ...)`: a map's full screen as RGBA pixels, its VR
  bounds' top left at pixel (0, 0), with optional overlays of footholds,
  ropes, portals and spawns, and spawns' hitboxes (`screen`).
- `write_png` writes them, and `render_path` is where
  `python -m game_data render` writes them by default:
  `<root>/renders/<map id>.png`.
- `STORED_AT_RX`: which `rx` puts a background at its stored position, the one
  reading of the client's parallax that the maintainer's visual check decides
  (`placement`).
- `RenderError`: the image store lacks an image the catalogue names, or the
  map has an item this doesn't know how to draw.

Where each item goes, and the order they're drawn in, is `placement`, ported
from the v83 module where it holds for Classic. This is the only layer that
imports `cv2`.
"""

from .placement import STORED_AT_RX, Camera
from .screen import RENDERS, VIEWPORT, RenderError, render_map, render_path, write_png

__all__ = [
    "RENDERS",
    "STORED_AT_RX",
    "VIEWPORT",
    "Camera",
    "RenderError",
    "render_map",
    "render_path",
    "write_png",
]
