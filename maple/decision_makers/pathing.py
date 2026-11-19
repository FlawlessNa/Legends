"""
Plain reads of the pathing data the rotation's planner makes.

`MovementsMixin` plans Paths on the map's foothold graph and keeps what it made
in `BotData` by name (`movement_handler`, `path`, `movements`). Until a Provider
serves that data (#442), what else reads it reads it through these functions,
which the mixin calls too (ADR 0004, "a ported DecisionMaker may read data an
unported one still makes"): `DESTINATION`'s Provider draws its destinations on
the platforms a Path reaches, and movement recovery reads the position.

They live beside the mixin rather than in it so that a Provider can import them:
the mixins import the Providers. They go with the mixin.
"""

from botting.core import BotData
from botting.screen import Reading
from maple.model.mechanics import MovementHandler
from maple.model.mechanics.physics import VRPhysics
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionSource, VirtualPosition


def read_position(data: BotData) -> Reading[VirtualPosition]:
    """
    `current_position`, read when it is stale; `UNSURE`, without a read, on a
    map no position is read on (the map not known, or with no minimap), where a
    read could only fail into the minimap's error handler.
    """
    world_map: WorldMap | None = getattr(data, "world_map", None)
    if world_map is None or world_map.minimap is None:
        return Reading.unsure(0.0, "no position is read on this map")
    return data.current_position


def read_resolution(position: VirtualPosition, world_map: WorldMap) -> float:
    """
    How far off a read's x may be, in virtual px: half a canvas px for a
    coarse read (the middle of the canvas pixel the feet are in), 0 for a
    fused one. A walk no longer than that is no move (#516,
    `MovementHandler.compute_path`).
    """
    if position.source is not PositionSource.COARSE or world_map.minimap is None:
        return 0.0
    return world_map.minimap.scale / 2


def current_physics(data: BotData) -> VRPhysics:
    """The character's physics, with its current speed and jump stats."""
    values = getattr(data, "game_physics", None)
    if values is None:
        raise ValueError("no game physics: the bot's map isn't known")
    return VRPhysics.from_game_files(
        values,
        speed_multiplier=data.speed_multiplier,
        jump_multiplier=data.jump_multiplier,
        calibration=getattr(data, "calibration", None),
    )


def reachable_platforms(data: BotData) -> tuple[Platform, ...] | None:
    """
    The platforms a Path reaches from the character's last position read, on
    the graph of its current physics. `None` while that isn't known: no
    `MovementHandler` yet (or none on this map), the graph of the current
    physics still building, no position read or an unsure one, or a position
    on no surface (in the air).

    Reads no position: it is the last one read. The graph is the handler's,
    and is never waited for: while it builds off the loop (#430), asking
    starts its build if nothing had, and answers `None`.
    """
    try:
        handler: MovementHandler | None = data.movement_handler
    except AttributeError:
        return None
    last = last_position(data)
    if handler is None or last is None:
        return None
    graph = handler.ready_graph(current_physics(data))
    if graph is None:
        return None
    try:
        surfaces = graph.reachable((last.x, last.y))
    except ValueError:
        return None
    platforms = tuple(s for s in surfaces if isinstance(s, Platform))
    return platforms or None


def last_position(data: BotData) -> VirtualPosition | None:
    """
    The last virtual position read, without reading one: `None` before the
    first read, or when the bot reads none.
    """
    try:
        last = data.get_last_known_value("current_position", update=False)
    except AttributeError:
        return None
    return None if last is None else last.value
