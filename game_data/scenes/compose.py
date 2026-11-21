"""
`compose_scene`: one synthetic client screen of a map, its mobs drawn near
their spawn points, and a label per mob.

**The mobs** are a map-wide population: a share of the map's mob spawn
points, drawn in `fill`, gets one mob each, so there are never more mobs than
spawn points. A mob is within `wander` pixels of its spawn point's `x`,
clamped to its **spot**: the extent of the spawn's foothold chain (`prev` and
`next`, walls skipped) inside `[rx0, rx1]`, so none hangs off a platform's
edge. `y` is the height of the chain at `x` (`_ground`). A flying mob is
raised by 0 to `FLY_LIFT` pixels, no higher than the view's top. Its action is
drawn among those it has of `ACTIONS`, its frame uniformly, and its facing
either way. They are drawn in a random order; the camera crops them.

**The view** is a camera of the `client`'s size following a character
(`scene_camera`): it stands at a point drawn on a spot, weighted by the spot's
width, and the camera's centre is `CAMERA_ABOVE_FEET` pixels above it, off by
up to `CAMERA_LAG` as when the character moves, then clamped so the view stays
inside the VR bounds. A map with no spot draws the centre uniformly in the VR
bounds instead (`draw_camera`). On an axis where the bounds are smaller than
the view, the map is centred and the rest is black, as the client shows it.
The background is `render_map` at that camera, with every animated item at one
`frame` drawn for the scene, cropped to the view, over black.

**Occluders**, each kind on when given: `drops` (`occluders.Drops`) lie at
kill sites, behind or in front of the mobs at random. A site's count is
`sites_per_mob` times the mobs with a pixel in the view, rounded; each is on a
spot overlapping the view, `x` uniform in its columns there, with `per_site`
drops fanned `spread` pixels apart on its ground. `damage`
(`occluders.Damage`) numbers are above mobs with a pixel in the view, in
front.

**Labels** (`draw_mobs`). A mob's box is the bounds of its drawn sprite's
opaque pixels (alpha > 0) inside the view, not its `lt`/`rb` hitbox.
`visible` is the share of those pixels that nothing drawn after it covers,
mobs and occluders alike. A label under `visibility_floor` is dropped; the
mob stays in the image.

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
from game_data.catalogue import (
    Bounds,
    Catalogue,
    Foothold,
    MapData,
    MobData,
    MobFrame,
    Spawn,
)
from game_data.render import VIEWPORT, Camera, Images, render_map
from game_data.render.placement import top_left

from . import occluders as occ
from .occluders import Damage, Drops, Overlay, Sprites, check_range

SCENES_VERSION: Final = 3
"""Bumped whenever the same arguments and seed would give another scene."""

ACTIONS: Final = ("stand", "move", "hit1", "die1")
"""The actions a mob is drawn in, among those it has."""

FILL: Final = (0.3, 1.0)
"""The share of a map's mob spawn points that has a mob, drawn per scene."""

WANDER: Final = 120
"""The most a mob is from its spawn point's `x`, in pixels."""

VISIBILITY_FLOOR: Final = 0.3
FLY_LIFT: Final = 150
"""The most a flying mob is raised above its foothold, in pixels."""

CAMERA_ABOVE_FEET: Final = 60
"""How far above the followed character's feet the camera's centre is."""

CAMERA_LAG: Final = (120, 40)
"""The most the camera's centre is off the character, `(x, y)`, in pixels."""

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


@dataclass(frozen=True, slots=True)
class Spot:
    """
    Where a spawn's mob can be: `[left, right]` on its foothold chain, in
    virtual coordinates.
    """

    spawn: Spawn
    left: int
    right: int


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
    fill: tuple[float, float] = FILL,
    wander: int = WANDER,
    visibility_floor: float = VISIBILITY_FLOOR,
    cameras: int | None = None,
    drops: Drops | None = None,
    damage: Damage | None = None,
) -> Scene:
    """
    One synthetic screen of a map, and its labels.

    :param map: Its name or ID, as `Catalogue.map` takes.
    :param client: The screen's width and height.
    :param fill: The fewest and most of the map's mob spawn points that have
        a mob, as shares from 0 to 1.
    :param wander: The most a mob is from its spawn point's `x`, in pixels.
    :param visibility_floor: A label whose `visible` is under it is dropped.
    :param cameras: `None` renders the background for each scene. An integer
        `n` renders `n` cameras of the map once, drawn from `rng` the first
        time this `rng` composes the map, and each scene picks one of them.
    :param drops: The map's drops; `None` draws none.
    :param damage: The map's damage numbers; `None` draws none.
    :raises LookupError: As `Catalogue.map` does.
    :raises SceneError: Two species of the map share a class name.
    :raises RenderError: As `render_map` does.
    :raises ValueError: `fill` isn't `0 <= min <= max <= 1`, `wander` is
        negative, `cameras` isn't positive, or the catalogue has no sprite for
        a drop or digit set asked for.
    """
    check_range("fill", fill)
    if fill[1] > 1:
        raise ValueError(f"fill is a share of the spawn points, at most 1, not {fill}")
    if wander < 0:
        raise ValueError(f"wander can't be negative, not {wander}")
    if cameras is not None and cameras < 1:
        raise ValueError(f"cameras must be positive, not {cameras}")
    data = cat.map(map)
    state = _state(cat, data, rng, client, cameras)
    pool = None if drops is None else state.sprites(cat).pool(drops)
    pairs = None if damage is None else state.sprites(cat).pairs(damage)
    if state.views:
        camera, view = state.views[int(rng.integers(len(state.views)))]
        view = view.copy()
    else:
        camera = scene_camera(data, state.spots, client, rng)
        view = _view(cat, data, camera, int(rng.integers(FRAMES)), state.images)
    placements = _placements(data, state, camera, fill, wander, rng)
    shown = [p for p in placements if _in_view(p, state.images, camera)]
    behind: list[Overlay] = []
    front: list[Overlay] = []
    if drops is not None and pool is not None:
        for overlay in _drops(data, state, camera, len(shown), drops, pool, rng):
            (front if rng.integers(2) else behind).append(overlay)
    if damage is not None and pairs is not None and shown:
        low, high = damage.count
        for _ in range(int(rng.integers(low, high + 1))):
            placement = shown[int(rng.integers(len(shown)))]
            x, y = _head(placement, state.images)
            front += occ.damage(pairs, damage.values, state.images, x, y, rng)
    for overlay in behind:
        _paste(view, overlay.pixels, overlay.left, overlay.top)
    drawn = draw_mobs(view, placements, state.images, front)
    labels = tuple(
        label
        for label in drawn
        if label is not None and label.visible >= visibility_floor
    )
    return Scene(view, labels)


def draw_mobs(
    view: np.ndarray,
    placements: Sequence[Placement],
    images: Images,
    overlays: Sequence[Overlay] = (),
) -> tuple[Label | None, ...]:
    """
    Draws the mobs over `view`, in place, in order, then the `overlays` over
    them, and labels each mob.

    :param view: `(height, width, 3)` RGB pixels.
    :param images: Where the frames' images are read.
    :param overlays: Occluders drawn in front of every mob, which count
        against each one's `visible`.
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
    for overlay in overlays:
        found = _paste(view, overlay.pixels, overlay.left, overlay.top)
        if found is not None:
            mask, (x0, y0, x1, y1) = found
            covered[y0:y1, x0:x1] |= mask
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
    spots: list[Spot]
    views: list[tuple[Camera, np.ndarray]]
    read: Sprites | None = None

    def sprites(self, cat: Catalogue) -> Sprites:
        """The catalogue's occluder sprites, read once."""
        if self.read is None:
            self.read = Sprites.read(cat)
        return self.read


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
    species = _species(cat, data)
    state = _State(images, species, spots(data, species), [])
    for _ in range(cameras or 0):
        camera = scene_camera(data, state.spots, client, rng)
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


def spots(data: MapData, species: dict[int, MobData]) -> list[Spot]:
    """
    The spot of each of the map's mob spawns of `species`, in the map's
    order: its foothold chain's extent (walls skipped) inside `[rx0, rx1]`.
    A spawn whose foothold the map lacks, or whose chain and range don't
    meet, is its own `x` alone.
    """
    own = {f.id: f for f in data.footholds if f.source == "map"}
    found: list[Spot] = []
    for spawn in data.spawns:
        if spawn.kind != "mob" or spawn.id not in species:
            continue
        low, high = min(spawn.rx0, spawn.rx1), max(spawn.rx0, spawn.rx1)
        chain = _chain_extent(own, spawn.foothold)
        if chain is not None and max(chain[0], low) <= min(chain[1], high):
            found.append(Spot(spawn, max(chain[0], low), min(chain[1], high)))
        else:
            found.append(Spot(spawn, spawn.x, spawn.x))
    return found


def _chain_extent(own: dict[int, Foothold], start_id: int) -> tuple[int, int] | None:
    """The x extent of the non-wall footholds chained to `start_id`."""
    start = own.get(start_id)
    if start is None:
        return None
    seen = {start.id}
    queue = [start]
    low: int | None = None
    high: int | None = None
    while queue:
        foothold = queue.pop()
        if foothold.x1 != foothold.x2:
            left, right = sorted((foothold.x1, foothold.x2))
            low = left if low is None else min(low, left)
            high = right if high is None else max(high, right)
        for link in (foothold.prev, foothold.next):
            found = own.get(link) if link else None
            if found is not None and found.id not in seen:
                seen.add(found.id)
                queue.append(found)
    return None if low is None or high is None else (low, high)


def scene_camera(
    data: MapData,
    spots: Sequence[Spot],
    client: tuple[int, int],
    rng: np.random.Generator,
) -> Camera:
    """
    A scene's camera, of the client's size, following a character standing
    on one of the `spots` (drawn by their width): its centre
    `CAMERA_ABOVE_FEET` above the feet and up to `CAMERA_LAG` off, clamped to
    the VR bounds. `draw_camera` when there's no spot.
    """
    if not spots:
        return draw_camera(data.vr, client, rng)
    widths = np.array([spot.right - spot.left + 1 for spot in spots], dtype=float)
    spot = spots[int(rng.choice(len(spots), p=widths / widths.sum()))]
    x = int(rng.integers(spot.left, spot.right + 1))
    y = _ground(data.footholds, spot.spawn, x)
    lag_x, lag_y = CAMERA_LAG
    centre_x = x + int(rng.integers(-lag_x, lag_x + 1))
    centre_y = y - CAMERA_ABOVE_FEET + int(rng.integers(-lag_y, lag_y + 1))
    width, height = client
    centred = Camera.centred(data.vr, client)
    return Camera(
        _clamped(centre_x, data.vr.left, data.vr.right, width, centred.left),
        _clamped(centre_y, data.vr.top, data.vr.bottom, height, centred.top),
        width,
        height,
    )


def draw_camera(
    bounds: Bounds, client: tuple[int, int], rng: np.random.Generator
) -> Camera:
    """
    A camera of the client's size: on each axis where the VR bounds are at
    least that size, its centre drawn uniformly in them and clamped so it
    stays inside; on one where they're smaller, the map centred.
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
    return _clamped(centre, low, high, size, centred)


def _clamped(centre: int, low: int, high: int, size: int, centred: int) -> int:
    """
    The camera's start on one axis for a centre, clamped to keep `size`
    inside `[low, high)`; `centred` when they're narrower.
    """
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
    state: _State,
    camera: Camera,
    fill: tuple[float, float],
    wander: int,
    rng: np.random.Generator,
) -> list[Placement]:
    """A mob near each of a `fill` share of the spots, in a random order."""
    if not state.spots:
        return []
    share = float(rng.uniform(fill[0], fill[1]))
    count = round(len(state.spots) * share)
    chosen = rng.choice(len(state.spots), size=count, replace=False)
    placements: list[Placement] = []
    for index in chosen:
        spot = state.spots[int(index)]
        mob = state.species[spot.spawn.id]
        x = spot.spawn.x + int(rng.integers(-wander, wander + 1))
        x = min(max(x, spot.left), spot.right)
        y = _ground(data.footholds, spot.spawn, x)
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


def _drops(
    data: MapData,
    state: _State,
    camera: Camera,
    shown: int,
    drops: Drops,
    pool: occ.Pool,
    rng: np.random.Generator,
) -> list[Overlay]:
    """
    The drops at the scene's kill sites: `sites_per_mob` per mob shown, each
    on a spot overlapping the view, its `per_site` drops fanned `spread`
    apart on the spot's ground.
    """
    right = camera.left + camera.width - 1
    near = [s for s in state.spots if s.left <= right and s.right >= camera.left]
    low, high = drops.sites_per_mob
    sites = round(shown * float(rng.uniform(low, high)))
    if not near:
        return []
    found: list[Overlay] = []
    for _ in range(sites):
        spot = near[int(rng.integers(len(near)))]
        centre = int(
            rng.integers(max(spot.left, camera.left), min(spot.right, right) + 1)
        )
        count = int(rng.integers(drops.per_site[0], drops.per_site[1] + 1))
        for n in range(count):
            offset = round((n - (count - 1) / 2) * drops.spread)
            jitter = int(rng.integers(-occ.DROP_JITTER, occ.DROP_JITTER + 1))
            x = min(max(centre + offset + jitter, spot.left), spot.right)
            y = _ground(data.footholds, spot.spawn, x)
            found.append(
                occ.drop(pool, state.images, x - camera.left, y - camera.top, rng)
            )
    return found


def _in_view(placement: Placement, images: Images, camera: Camera) -> bool:
    """Whether any of a placed mob's opaque pixels is in the view."""
    pixels, left, top = _sprite(placement, images)
    x0, y0 = max(-left, 0), max(-top, 0)
    x1 = min(camera.width - left, pixels.shape[1])
    y1 = min(camera.height - top, pixels.shape[0])
    return x0 < x1 and y0 < y1 and bool((pixels[y0:y1, x0:x1, 3] > 0).any())


def _head(placement: Placement, images: Images) -> tuple[int, int]:
    """Where a placed mob's head is in the view (`occluders.head`)."""
    frame = _frame(placement)
    pixels, left, top = _sprite(placement, images)
    head_at = None
    if frame.head_x is not None and frame.head_y is not None:
        head_x = -frame.head_x if placement.flip else frame.head_x
        head_at = (placement.x + head_x, placement.y + frame.head_y)
    return occ.head(pixels, left, top, head_at)


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


def _frame(placement: Placement) -> MobFrame:
    """The placement's frame of its mob."""
    for frame in placement.mob.frames:
        if frame.action == placement.action and frame.frame == placement.frame:
            return frame
    raise LookupError(
        f"mob {placement.mob.id} has no frame {placement.action}/{placement.frame}"
    )


def _sprite(placement: Placement, images: Images) -> tuple[Pixels, int, int]:
    """The placement's RGBA pixels, mirrored when flipped, and their top left."""
    frame = _frame(placement)
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
