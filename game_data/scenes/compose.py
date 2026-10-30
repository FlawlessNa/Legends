"""
`compose_scene`: one synthetic client screen of a map, its mobs drawn on their
spawns, and a label per mob.

**The view** is a camera of the `client`'s size. On an axis where the map's VR
bounds are at least that size, its centre is drawn uniformly in the bounds,
then clamped so the view stays inside them. On an axis where they are smaller,
the map is centred and the rest is black, as the client shows it. The
background is `render_map` at that camera, with every animated item at one
`frame` drawn for the scene, cropped to the view, over black.

**The mobs.** Their number is drawn from `mobs`. Each comes from a spawn drawn
uniformly among the map's `mob` spawns whose `[rx0, rx1]` overlaps the view's
columns: its species, an `x` uniform in `[rx0, rx1]`, and `y` the height of its
foothold at `x` (`_ground`). A flying mob is raised by 0 to `FLY_LIFT` pixels,
no higher than the view's top. Its action is drawn among those it has of
`ACTIONS`, its frame uniformly, and its facing either way. They are drawn in a
random order.

**Labels** (`draw_mobs`). A mob's box is the bounds of its drawn sprite's
opaque pixels (alpha > 0) inside the view, not its `lt`/`rb` hitbox.
`visible` is the share of those pixels that nothing drawn after it covers. A
label under `visibility_floor` is dropped; the mob stays in the image.

**Determinism.** Every draw comes from the `rng`, in a fixed order, so the
same catalogue, map, arguments and seed give the same scene.
`SCENES_VERSION` changes whenever that output would.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from game_data.archive import Pixels
from game_data.catalogue import Bounds, Catalogue, Foothold, MapData, MobData, Spawn
from game_data.render import VIEWPORT, Camera, Images, render_map
from game_data.render.placement import top_left

SCENES_VERSION: Final = 1
"""Bumped whenever the same arguments and seed would give another scene."""

ACTIONS: Final = ("stand", "move", "hit1", "die1")
"""The actions a mob is drawn in, among those it has."""

MOBS: Final = (0, 15)
VISIBILITY_FLOOR: Final = 0.3
FLY_LIFT: Final = 150
"""The most a flying mob is raised above its foothold, in pixels."""

FRAMES: Final = 720720
"""
The background's `frame` is drawn in `[0, FRAMES)`. It is the least common
multiple of 1 to 16, so an item of up to 16 frames is at each equally often.
"""

# How many footholds along a spawn's chain are searched for its `x`.
_CHAIN: Final = 64

_log = logging.getLogger(__name__)


class SceneError(Exception):
    """A map's mobs can't be told apart: two species share a class name."""


@dataclass(frozen=True, slots=True)
class Label:
    """
    One mob's label.

    :ivar cls: Its class name (`class_name`).
    :ivar box: `(x1, y1, x2, y2)`, in the view's pixels: the bounds of its
        opaque pixels in the view, `x2` and `y2` one past the last.
    :ivar visible: The share of those pixels nothing drawn after it covers.
    """

    cls: str
    box: tuple[int, int, int, int]
    visible: float


@dataclass(frozen=True, slots=True)
class Scene:
    """
    :ivar image: `(height, width, 3)` RGB pixels, the client's size.
    :ivar labels: A label per mob drawn above the visibility floor, in the
        order the mobs were drawn.
    """

    image: np.ndarray
    labels: tuple[Label, ...]


@dataclass(frozen=True, slots=True)
class Placement:
    """
    A mob to draw: its `action`'s frame numbered `frame`, its origin at view
    pixel `(x, y)`, mirrored about `x` when `flip`.
    """

    mob: MobData
    action: str
    frame: int
    x: int
    y: int
    flip: bool


def class_name(name: str) -> str:
    """
    A mob's class, the form the bot compares a model's classes with: its name
    with spaces and dots removed.
    """
    return name.replace(" ", "").replace(".", "")


def map_classes(cat: Catalogue, map: str | int) -> list[str]:
    """
    The classes a map's scenes can label, sorted by name: those of the species
    `compose_scene` draws.

    :param map: Its name or ID, as `Catalogue.map` takes.
    :raises LookupError: As `Catalogue.map` does.
    :raises SceneError: Two species of the map share a class name.
    """
    species = _species(cat, cat.map(map))
    return sorted(class_name(str(mob.name)) for mob in species.values())


def compose_scene(
    cat: Catalogue,
    map: str | int,
    rng: np.random.Generator,
    *,
    client: tuple[int, int] = VIEWPORT,
    mobs: tuple[int, int] = MOBS,
    visibility_floor: float = VISIBILITY_FLOOR,
    cameras: int | None = None,
) -> Scene:
    """
    One synthetic screen of a map, and its labels.

    :param map: Its name or ID, as `Catalogue.map` takes.
    :param client: The screen's width and height.
    :param mobs: The fewest and most mobs drawn, both included.
    :param visibility_floor: A label whose `visible` is under it is dropped.
    :param cameras: `None` renders the background for each scene. An integer
        `n` renders `n` cameras of the map once, drawn from `rng` the first
        time this `rng` composes the map, and each scene picks one of them.
    :raises LookupError: As `Catalogue.map` does.
    :raises SceneError: Two species of the map share a class name.
    :raises RenderError: As `render_map` does.
    :raises ValueError: `mobs` isn't `0 <= min <= max`, or `cameras` isn't
        positive.
    """
    low, high = mobs
    if not 0 <= low <= high:
        raise ValueError(f"mobs must be (min, max) with 0 <= min <= max, not {mobs}")
    if cameras is not None and cameras < 1:
        raise ValueError(f"cameras must be positive, not {cameras}")
    data = cat.map(map)
    state = _state(cat, data, rng, client, cameras)
    if state.views:
        camera, view = state.views[int(rng.integers(len(state.views)))]
        view = view.copy()
    else:
        camera = draw_camera(data.vr, client, rng)
        view = _view(cat, data, camera, int(rng.integers(FRAMES)), state.images)
    count = int(rng.integers(low, high + 1))
    placements = _placements(data, state.species, camera, count, rng)
    drawn = draw_mobs(view, placements, state.images)
    labels = tuple(
        label
        for label in drawn
        if label is not None and label.visible >= visibility_floor
    )
    return Scene(view, labels)


def draw_mobs(
    view: np.ndarray, placements: Sequence[Placement], images: Images
) -> tuple[Label | None, ...]:
    """
    Draws the mobs over `view`, in place, in order, and labels each.

    :param view: `(height, width, 3)` RGB pixels.
    :param images: Where the frames' images are read.
    :returns: One label per placement, in their order, none floored; `None`
        for a mob with no opaque pixel in the view.
    :raises LookupError: A placement's mob has no such frame, or no image for
        it.
    """
    height, width = view.shape[:2]
    masks: list[tuple[np.ndarray, tuple[int, int, int, int]] | None] = []
    for placement in placements:
        sprite, left, top = _sprite(placement, images)
        masks.append(_paste(view, sprite, left, top))
    covered = np.zeros((height, width), dtype=bool)
    labels: list[Label | None] = []
    for placement, found in zip(reversed(placements), reversed(masks), strict=True):
        if found is None:
            labels.append(None)
            continue
        mask, (x0, y0, x1, y1) = found
        region = covered[y0:y1, x0:x1]
        opaque = int(mask.sum())
        seen = int((mask & ~region).sum())
        region |= mask
        rows = np.flatnonzero(mask.any(axis=1))
        columns = np.flatnonzero(mask.any(axis=0))
        box = (
            x0 + int(columns[0]),
            y0 + int(rows[0]),
            x0 + int(columns[-1]) + 1,
            y0 + int(rows[-1]) + 1,
        )
        name = placement.mob.name or str(placement.mob.id)
        labels.append(Label(class_name(name), box, seen / opaque))
    return tuple(reversed(labels))


@dataclass(slots=True)
class _State:
    """What a map's scenes share, for one `rng`."""

    images: Images
    species: dict[int, MobData]
    views: list[tuple[Camera, np.ndarray]]


type _Key = tuple[str, str, int, tuple[int, int], int | None]

_KEPT: Final = 8
"""
How many generators' states are kept, the latest used. A generator's state is
keyed by its identity, so that a fresh one of the same seed starts over; it
can't be weakly referenced, so each entry holds it, which keeps its `id` from
being reused while kept. A generator that falls out draws its cameras again.
"""

_STATES: Final = dict[int, tuple[np.random.Generator, dict[_Key, _State]]]()


def _state(
    cat: Catalogue,
    data: MapData,
    rng: np.random.Generator,
    client: tuple[int, int],
    cameras: int | None,
) -> _State:
    kept = _STATES.pop(id(rng), None)
    states = {} if kept is None else kept[1]
    _STATES[id(rng)] = (rng, states)
    while len(_STATES) > _KEPT:
        del _STATES[next(iter(_STATES))]
    key = (cat.build, str(cat.store.root), data.id, client, cameras)
    found = states.get(key)
    if found is not None:
        return found
    images = Images(cat.store.images)
    state = _State(images, _species(cat, data), [])
    for _ in range(cameras or 0):
        camera = draw_camera(data.vr, client, rng)
        frame = int(rng.integers(FRAMES))
        state.views.append((camera, _view(cat, data, camera, frame, images)))
    states[key] = state
    return state


def _species(cat: Catalogue, data: MapData) -> dict[int, MobData]:
    """
    The map's mob species that can be drawn, by ID: those the catalogue has,
    with a name and a frame of `ACTIONS` with an image. The others are left
    out, with a warning naming them.

    :raises SceneError: Two of them share a class name.
    """
    found: dict[int, MobData] = {}
    by_class: dict[str, int] = {}
    for mob_id in dict.fromkeys(s.id for s in data.spawns if s.kind == "mob"):
        try:
            mob = cat.mob(mob_id)
        except LookupError:
            _log.warning(
                "map %s: mob %s isn't in the catalogue; left out", data.id, mob_id
            )
            continue
        if mob.name is None:
            _log.warning("map %s: mob %s has no name; left out", data.id, mob_id)
            continue
        if not _actions(mob):
            _log.warning(
                "map %s: %s (%s) has no sprite; left out", data.id, mob.name, mob_id
            )
            continue
        cls = class_name(mob.name)
        if cls in by_class:
            raise SceneError(
                f"map {data.id}: mobs {by_class[cls]} and {mob_id} share the class "
                f"name {cls!r}"
            )
        by_class[cls] = mob_id
        found[mob_id] = mob
    return found


def _actions(mob: MobData) -> dict[str, list[int]]:
    """The frames with an image of each of `ACTIONS` the mob has, by action."""
    found: dict[str, list[int]] = {}
    for frame in mob.frames:
        if frame.action in ACTIONS and frame.image is not None:
            found.setdefault(frame.action, []).append(frame.frame)
    return {action: found[action] for action in ACTIONS if action in found}


def draw_camera(
    bounds: Bounds, client: tuple[int, int], rng: np.random.Generator
) -> Camera:
    """
    A scene's camera, of the client's size: on each axis where the VR bounds
    are at least that size, its centre drawn uniformly in them and clamped so
    it stays inside; on one where they're smaller, the map centred.
    """
    width, height = client
    centred = Camera.centred(bounds, client)
    return Camera(
        _axis(bounds.left, bounds.right, width, centred.left, rng),
        _axis(bounds.top, bounds.bottom, height, centred.top, rng),
        width,
        height,
    )


def _axis(
    low: int, high: int, size: int, centred: int, rng: np.random.Generator
) -> int:
    """
    The camera's start on one axis: its centre drawn in `[low, high)` and
    clamped to keep `size` inside them; `centred` when they're narrower.
    """
    centre = int(rng.integers(low, max(high, low + 1)))
    if high - low < size:
        return centred
    half = size // 2
    return min(max(centre, low + half), high - size + half) - half


def _view(
    cat: Catalogue, data: MapData, camera: Camera, frame: int, images: Images
) -> np.ndarray:
    """The map at `camera`, cropped to it, over black, as RGB."""
    screen = render_map(cat, data.id, frame=frame, camera=camera, images=images)
    view = np.zeros((camera.height, camera.width, 3), dtype=np.uint8)
    _paste(view, screen, data.vr.left - camera.left, data.vr.top - camera.top)
    return view


def _placements(
    data: MapData,
    species: dict[int, MobData],
    camera: Camera,
    count: int,
    rng: np.random.Generator,
) -> list[Placement]:
    right = camera.left + camera.width
    spawns = [
        spawn
        for spawn in data.spawns
        if spawn.kind == "mob"
        and spawn.id in species
        and min(spawn.rx0, spawn.rx1) < right
        and max(spawn.rx0, spawn.rx1) >= camera.left
    ]
    if not spawns:
        return []
    placements: list[Placement] = []
    for _ in range(count):
        spawn = spawns[int(rng.integers(len(spawns)))]
        mob = species[spawn.id]
        x = int(rng.integers(min(spawn.rx0, spawn.rx1), max(spawn.rx0, spawn.rx1) + 1))
        y = _ground(data.footholds, spawn, x)
        if mob.fly_speed is not None:
            y = max(y - int(rng.integers(FLY_LIFT + 1)), camera.top)
        actions = _actions(mob)
        action = list(actions)[int(rng.integers(len(actions)))]
        frames = actions[action]
        frame = frames[int(rng.integers(len(frames)))]
        flip = bool(rng.integers(2))
        placements.append(
            Placement(mob, action, frame, x - camera.left, y - camera.top, flip)
        )
    rng.shuffle(placements)
    return placements


def _ground(footholds: Iterable[Foothold], spawn: Spawn, x: int) -> int:
    """
    The height at `x` of the ground the spawn stands on: its foothold, or the
    first along the foothold's chain (`prev` and `next`) that spans `x`.
    Walls are skipped. When none spans it, the nearest end of the spawn's
    foothold; when the map has no such foothold, the spawn's `cy`.
    """
    own = {f.id: f for f in footholds if f.source == "map"}
    start = own.get(spawn.foothold)
    if start is None:
        return spawn.cy
    seen = {start.id}
    queue = [start]
    for _ in range(_CHAIN):
        if not queue:
            break
        foothold = queue.pop(0)
        if foothold.x1 != foothold.x2 and _spans(foothold, x):
            return _height(foothold, x)
        for link in (foothold.prev, foothold.next):
            found = own.get(link) if link else None
            if found is not None and found.id not in seen:
                seen.add(found.id)
                queue.append(found)
    return _height(start, min(max(x, min(start.x1, start.x2)), max(start.x1, start.x2)))


def _spans(foothold: Foothold, x: int) -> bool:
    return min(foothold.x1, foothold.x2) <= x <= max(foothold.x1, foothold.x2)


def _height(foothold: Foothold, x: int) -> int:
    if foothold.x1 == foothold.x2:
        return min(foothold.y1, foothold.y2)
    share = (x - foothold.x1) / (foothold.x2 - foothold.x1)
    return round(foothold.y1 + share * (foothold.y2 - foothold.y1))


def _sprite(placement: Placement, images: Images) -> tuple[Pixels, int, int]:
    """The placement's RGBA pixels, mirrored when flipped, and their top left."""
    for frame in placement.mob.frames:
        if frame.action == placement.action and frame.frame == placement.frame:
            break
    else:
        raise LookupError(
            f"mob {placement.mob.id} has no frame {placement.action}/{placement.frame}"
        )
    if frame.image is None:
        raise LookupError(
            f"mob {placement.mob.id}'s frame {placement.action}/{placement.frame} "
            "has no image"
        )
    pixels = images.get(frame.image)
    origin = (frame.origin_x, frame.origin_y)
    width = pixels.shape[1]
    left, top = top_left(placement.x, placement.y, origin, width, placement.flip)
    return (pixels[:, ::-1] if placement.flip else pixels), left, top


def _paste(
    view: np.ndarray, pixels: Pixels, left: int, top: int
) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    """
    Lays RGBA `pixels` over the RGB `view` by their alpha, top left at
    `(left, top)`.

    :returns: Their opaque pixels in the view, as a mask, and the region of
        the view `(x0, y0, x1, y1)` it covers; `None` when there are none.
    """
    height, width = pixels.shape[:2]
    x0, y0 = max(left, 0), max(top, 0)
    x1 = min(left + width, view.shape[1])
    y1 = min(top + height, view.shape[0])
    if x0 >= x1 or y0 >= y1:
        return None
    source = pixels[y0 - top : y1 - top, x0 - left : x1 - left]
    alpha = source[..., 3:].astype(np.float32) / 255
    target = view[y0:y1, x0:x1].astype(np.float32)
    colour = source[..., :3].astype(np.float32) * alpha + target * (1 - alpha)
    view[y0:y1, x0:x1] = np.rint(colour).astype(np.uint8)
    mask = source[..., 3] > 0
    if not mask.any():
        return None
    return mask, (x0, y0, x1, y1)
