"""
`render_map`: a map's full screen, in virtual coordinates, as RGBA pixels.

The map's VR bounds' top left is pixel (0, 0), and the image is the bounds'
width by their height, times `scale`. Nothing drawn is a transparent pixel.
Each item is laid over what's drawn before it by its alpha (`placement` says
where, and in what order).

**Overlays**, with `overlays=True`, are drawn over the whole screen, after it
is scaled, so that they stay one pixel wide:

| what                                  | colour (RGBA)        |
| ------------------------------------- | -------------------- |
| the map's own footholds               | white                |
| footholds drawn on tiles              | blue                 |
| footholds drawn on objects            | green                |
| the map's own ropes and ladders       | cyan                 |
| ropes and ladders drawn on objects    | yellow               |
| portals, a dot at each                | red                  |
| a spawn with no sprite to draw, a dot | orange               |
| a spawn's body hitbox, `hitboxes`     | magenta              |

The colours of footholds, ropes and portals are the v83 module's
(`map_parser.py`). Each mob spawn is drawn, before scaling, as its mob's first
`stand` frame (`fly` for a mob that has no `stand`), standing at `(x, cy)`,
mirrored when the spawn is flipped. An NPC, a mob the catalogue doesn't have,
or a frame with no image gets an orange dot instead. Hidden spawns are drawn
too.

`hitboxes=True` draws the spawns, and each one's `lt`/`rb` box, relative to
where it stands, mirrored with it. It does so with or without the other
overlays.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Final

import cv2
import numpy as np

from game_data.archive import Pixels
from game_data.catalogue import (
    Catalogue,
    MapData,
    MapLayer,
    MobData,
    MobFrame,
    Spawn,
)
from game_data.extraction import ImageStore

from .placement import Camera, background_position, copies, draw_order, frame_at
from .placement import top_left as place

RENDERS: Final = "renders"
VIEWPORT: Final = (1366, 768)

type Colour = tuple[int, int, int, int]

FOOTHOLD: Final[dict[str, Colour]] = {
    "map": (255, 255, 255, 255),
    "tile": (0, 0, 255, 255),
    "object": (0, 255, 0, 255),
}
ROPE: Final[dict[str, Colour]] = {
    "map": (0, 255, 255, 255),
    "object": (255, 255, 0, 255),
}
PORTAL: Final[Colour] = (255, 0, 0, 255)
NO_SPRITE: Final[Colour] = (255, 128, 0, 255)
HITBOX: Final[Colour] = (255, 0, 255, 255)
DOT: Final = 3

# The action a spawn is drawn in, and the one a mob without it falls back on.
STAND: Final = ("stand", "fly")


class RenderError(Exception):
    """
    A map can't be drawn: the image store lacks an image the catalogue names,
    or the map has an item this doesn't know how to draw. It names the map or
    the image.
    """


def render_map(
    cat: Catalogue,
    map: str | int,
    *,
    scale: float = 1.0,
    frame: int = 0,
    viewport: tuple[int, int] = VIEWPORT,
    overlays: bool = False,
    hitboxes: bool = False,
) -> Pixels:
    """
    A map's full screen, as `(height, width, 4)` RGBA pixels.

    :param map: Its name or ID, as `Catalogue.map` takes.
    :param scale: Both sides are multiplied by it, and rounded.
    :param frame: The frame animated items are drawn at, `frame % frame_count`.
    :param viewport: The camera's size, in pixels. The backgrounds are placed
        for a camera of that size centred on the map: their parallax moves
        them by the camera's centre, which a centred camera puts at the map's
        centre whatever its size, so it changes them only by rounding.
    :param overlays: Draw footholds, ropes, portals and spawns.
    :param hitboxes: Draw spawns with their body hitboxes.
    :raises LookupError: As `Catalogue.map` does.
    :raises RenderError: The image store lacks an image the catalogue names;
        or the map has a layer or a background type this doesn't know.
    :raises ValueError: `scale` isn't positive.
    """
    if scale <= 0:
        raise ValueError(f"a scale must be positive, not {scale}")
    data = cat.map(map)
    images = _Images(cat.store.images)
    bounds = data.vr
    screen = np.zeros(
        (bounds.bottom - bounds.top, bounds.right - bounds.left, 4), dtype=np.uint8
    )
    camera = Camera.centred(bounds, viewport)
    try:
        for item in draw_order(cat.map_layers(data.id)):
            _draw_item(screen, images, item, frame, camera, data)
    except ValueError as error:
        raise RenderError(f"map {data.id}: {error}") from error
    spawns = _spawns(cat, data) if overlays or hitboxes else []
    for spawn, sprite in spawns:
        if sprite is not None and sprite.image is not None:
            _paste_frame(screen, images.get(sprite.image), sprite, spawn, data)
    if scale != 1.0:
        screen = _scaled(screen, scale)
    if overlays:
        _draw_geometry(screen, data, scale)
    for spawn, sprite in spawns:
        if overlays and (sprite is None or sprite.image is None):
            _dot(screen, _at(spawn.x, spawn.cy, data, scale), NO_SPRITE)
        if hitboxes and sprite is not None:
            _draw_hitbox(screen, spawn, sprite, data, scale)
    return screen


def render_path(cat: Catalogue, map_id: int) -> Path:
    """Where `python -m game_data render` writes a map by default."""
    return cat.store.root / RENDERS / f"{map_id}.png"


def write_png(pixels: Pixels, path: Path) -> None:
    """Writes RGBA pixels to `path` as a PNG, creating its folder."""
    ok, encoded = cv2.imencode(".png", cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGRA))
    if not ok:
        raise RenderError(f"{path}: the pixels couldn't be encoded as a PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(np.asarray(encoded, dtype=np.uint8).tobytes())


class _Images:
    """The image store's images, each read once per render, as RGBA."""

    def __init__(self, store: ImageStore) -> None:
        self._store = store
        self._read: dict[str, Pixels] = {}

    def get(self, name: str) -> Pixels:
        found = self._read.get(name)
        if found is not None:
            return found
        path = self._store.path(name)
        try:
            data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        except FileNotFoundError:
            raise RenderError(
                f"the image store has no image {name}, which the catalogue names "
                f"({path})"
            ) from None
        decoded = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if decoded is None or decoded.ndim != 3 or decoded.shape[2] != 4:
            raise RenderError(f"{path} isn't an RGBA PNG")
        pixels = np.ascontiguousarray(
            cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGBA), dtype=np.uint8
        )
        self._read[name] = pixels
        return pixels


def _draw_item(
    screen: Pixels,
    images: _Images,
    item: MapLayer,
    frame: int,
    camera: Camera,
    data: MapData,
) -> None:
    found = frame_at(item, frame)
    if found is None or found.image is None:
        return
    pixels = images.get(found.image)
    origin = (found.origin_x, found.origin_y)
    height, width = pixels.shape[:2]
    if item.flip:
        pixels = pixels[:, ::-1]
    if item.background is None:
        x, y = place(item.x, item.y, origin, width, item.flip)
        _paste(screen, pixels, x - data.vr.left, y - data.vr.top)
        return
    x, y = background_position(item, camera)
    left, top = place(x, y, origin, width, item.flip)
    opacity = item.background.a / 255
    for x, y in copies(item, left, top, (width, height), data.vr):
        _paste(screen, pixels, x - data.vr.left, y - data.vr.top, opacity)


def _paste(
    screen: Pixels, pixels: Pixels, left: int, top: int, opacity: float = 1.0
) -> None:
    """Lays `pixels` over `screen` by their alpha, top left at `(left, top)`."""
    height, width = pixels.shape[:2]
    x0, y0 = max(left, 0), max(top, 0)
    x1 = min(left + width, screen.shape[1])
    y1 = min(top + height, screen.shape[0])
    if x0 >= x1 or y0 >= y1:
        return
    source = pixels[y0 - top : y1 - top, x0 - left : x1 - left].astype(np.float32)
    target = screen[y0:y1, x0:x1].astype(np.float32)
    alpha = source[..., 3:] / 255 * opacity
    below = target[..., 3:] / 255 * (1 - alpha)
    out_alpha = alpha + below
    colour = source[..., :3] * alpha + target[..., :3] * below
    colour = np.divide(
        colour, out_alpha, out=np.zeros_like(colour), where=out_alpha > 0
    )
    screen[y0:y1, x0:x1, :3] = np.rint(colour).astype(np.uint8)
    screen[y0:y1, x0:x1, 3:] = np.rint(out_alpha * 255).astype(np.uint8)


def _spawns(cat: Catalogue, data: MapData) -> list[tuple[Spawn, MobFrame | None]]:
    """Each spawn with the frame it's drawn as; `None` for none to draw."""
    mobs: dict[int, MobData | None] = {}
    found: list[tuple[Spawn, MobFrame | None]] = []
    for spawn in data.spawns:
        sprite = None
        if spawn.kind == "mob":
            if spawn.id not in mobs:
                try:
                    mobs[spawn.id] = cat.mob(spawn.id)
                except LookupError:
                    mobs[spawn.id] = None
            mob = mobs[spawn.id]
            sprite = None if mob is None else _first_stand(mob.frames)
        found.append((spawn, sprite))
    return found


def _first_stand(frames: Iterable[MobFrame]) -> MobFrame | None:
    by_action: dict[str, MobFrame] = {}
    for frame in frames:
        current = by_action.get(frame.action)
        if current is None or frame.frame < current.frame:
            by_action[frame.action] = frame
    for action in STAND:
        if action in by_action:
            return by_action[action]
    return None


def _paste_frame(
    screen: Pixels, pixels: Pixels, sprite: MobFrame, spawn: Spawn, data: MapData
) -> None:
    width = pixels.shape[1]
    origin = (sprite.origin_x, sprite.origin_y)
    x, y = place(spawn.x, spawn.cy, origin, width, spawn.flip)
    if spawn.flip:
        pixels = pixels[:, ::-1]
    _paste(screen, pixels, x - data.vr.left, y - data.vr.top)


def _scaled(screen: Pixels, scale: float) -> Pixels:
    height, width = screen.shape[:2]
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_NEAREST
    return np.asarray(
        cv2.resize(screen, size, interpolation=interpolation), dtype=np.uint8
    )


def _at(x: int, y: int, data: MapData, scale: float) -> tuple[int, int]:
    """A virtual point, as a pixel of the scaled screen."""
    return round((x - data.vr.left) * scale), round((y - data.vr.top) * scale)


def _draw_geometry(screen: Pixels, data: MapData, scale: float) -> None:
    # The map's own last: tiles' and objects' often lie on them.
    for foothold in sorted(data.footholds, key=lambda f: f.source == "map"):
        _line(
            screen,
            _at(foothold.x1, foothold.y1, data, scale),
            _at(foothold.x2, foothold.y2, data, scale),
            FOOTHOLD[foothold.source],
        )
    for rope in sorted(data.ropes, key=lambda r: r.source == "map"):
        _line(
            screen,
            _at(rope.x, rope.y1, data, scale),
            _at(rope.x, rope.y2, data, scale),
            ROPE[rope.source],
        )
    for portal in data.portals:
        _dot(screen, _at(portal.x, portal.y, data, scale), PORTAL)


def _draw_hitbox(
    screen: Pixels, spawn: Spawn, sprite: MobFrame, data: MapData, scale: float
) -> None:
    lt_x, lt_y, rb_x, rb_y = sprite.lt_x, sprite.lt_y, sprite.rb_x, sprite.rb_y
    if lt_x is None or lt_y is None or rb_x is None or rb_y is None:
        return
    if spawn.flip:
        lt_x, rb_x = -rb_x, -lt_x
    _rectangle(
        screen,
        _at(spawn.x + lt_x, spawn.cy + lt_y, data, scale),
        _at(spawn.x + rb_x, spawn.cy + rb_y, data, scale),
        HITBOX,
    )


def _line(
    screen: Pixels, start: tuple[int, int], end: tuple[int, int], colour: Colour
) -> None:
    cv2.line(screen, start, end, colour, 1)


def _rectangle(
    screen: Pixels, start: tuple[int, int], end: tuple[int, int], colour: Colour
) -> None:
    cv2.rectangle(screen, start, end, colour, 1)


def _dot(screen: Pixels, centre: tuple[int, int], colour: Colour) -> None:
    cv2.circle(screen, centre, DOT, colour, -1)
