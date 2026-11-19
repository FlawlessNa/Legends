"""
The decision makers on virtual positions (#398), against synthetic `WorldMap`s:
the rotation's destinations on platforms a Path reaches (`DestinationProvider`),
the wander a Claim steers it into, and the ladder check before a cast. No game
client, no game data store.
"""

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from botting.core import BotData, Providers, StartupRefused
from botting.logging_config import bucket_for
from botting.screen import Reading
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.decision_makers.providers import (
    DESTINATION,
    DESTINATION_PLATFORM,
    POSITION,
    WORLD_MAP,
    DestinationProvider,
    MapProvider,
    MinimapProvider,
    PathingProvider,
    wander,
)
from maple.decision_makers.providers import destination as destination_module
from maple.decision_makers.providers.sources.random import RandomSource
from maple.decision_makers.providers.sources.smart import SmartSource
from maple.decision_makers.recovery import MovementRecovery
from maple.model.navigation import FootholdGraph
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from maple.telemetry_events import MOVEMENT_TARGET_REACHED
from tests.test_maple.movement_lab import corpus
from tests.test_maple.movement_lab.fixture_maps import portal_pair, rope_grab
from tests.test_maple.serving import destination, override, pathing

#: A floor 0-300 at y 0, a floor 600-900 at y -400, and a portal from the
#: lower to the upper only: from the upper floor, the lower one is unreachable.
PORTALS = WorldMap.from_map_data(portal_pair())
LOWER, UPPER = PORTALS.platforms


class _Character:
    skills: dict[str, object] = {}  # noqa: RUF012


@dataclass
class _Rotation:
    """The rotation's two Providers: its destination, and the pathing to it."""

    provider: DestinationProvider
    planner: PathingProvider

    @property
    def data(self) -> BotData:
        return self.planner.data


def _data() -> BotData:
    data = BotData("T")
    data.set_static("ign", "T")
    return data


def _destination(
    world: WorldMap | None, at: Callable[[], Reading[VirtualPosition]]
) -> DestinationProvider:
    return destination(
        world,  # pyright: ignore[reportArgumentType] - a Bot with no map is refused
        at,
        data=_data(),
        game_physics=corpus.LAB_PHYSICS_VALUES,
    )


def _fused(x: float, y: float) -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(x, y, PositionSource.FUSED), 0.0)


def _rotation(
    at: Callable[[], Reading[VirtualPosition]], *, wait: bool = True
) -> _Rotation:
    """
    Destinations made before planning: the first is drawn blind, as
    `DestinationProvider` is set up before the pathing that plans to it. The
    graph builds off the loop from the pathing's setup on (#430); until it is
    built, destinations are drawn blind too. `wait` waits for it, as a Session
    does after its first seconds.
    """
    provider = _destination(PORTALS, at)
    planner = pathing(PORTALS, at, data=provider.data, character=_Character())
    if wait:
        planner.data.movement_handler.graph(planner.physics())
    return _Rotation(provider, planner)


def test_a_target_is_drawn_blind_while_the_graph_builds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Reachability needs the graph of the current physics. While it builds off the
    loop, asking never waits for it: the target is drawn as before a position is
    read, and checked once the graph is there.
    """
    reached, release = threading.Event(), threading.Event()
    build_graph = FootholdGraph._build_graph

    def held(graph: FootholdGraph) -> None:
        reached.set()
        assert release.wait(5), "the test never let the build go on"
        build_graph(graph)

    monkeypatch.setattr(FootholdGraph, "_build_graph", held)
    try:
        rotation = _rotation(lambda: _fused(750.0, -400.0), wait=False)
        assert reached.wait(5)  # the graph is half-built in the worker
        asked = time.perf_counter()
        rotation.data.update_attribute(DESTINATION.name)
        assert time.perf_counter() - asked < 1.0  # the build is held for up to 5 s
        assert rotation.planner.reachable_platforms() is None
    finally:
        release.set()

    rotation.data.movement_handler.graph(rotation.planner.physics())
    assert rotation.planner.reachable_platforms() == (UPPER,)


def test_a_rotation_needs_the_bots_map() -> None:
    with pytest.raises(StartupRefused, match="map isn't known"):
        _destination(None, lambda: _fused(0.0, 0.0))


def test_the_first_target_is_drawn_on_any_platform_before_a_position_is_read() -> None:
    random.seed(0)
    unread = Reading.unsure(0.0, "not read yet")

    targets = {_rotation(lambda: unread).data.read(DESTINATION) for _ in range(30)}

    on = {PORTALS.platform_at(t) for t in targets}
    assert on == {LOWER, UPPER}


def test_a_blind_target_no_path_reaches_is_drawn_again_once_placed() -> None:
    """
    From the upper floor nothing reaches the lower one: a first target drawn
    there, before the position was known, is replaced on the next update.
    """
    random.seed(1)
    for _ in range(20):
        rotation = _rotation(lambda: _fused(750.0, -400.0))
        rotation.data.update_attribute(DESTINATION.name)
        assert PORTALS.platform_at(rotation.data.read(DESTINATION)) == UPPER


def test_a_reached_target_is_followed_by_one_a_path_reaches() -> None:
    random.seed(2)
    rotation = _rotation(lambda: _fused(750.0, -400.0))
    for _ in range(20):
        # Within arrival of the feet.
        rotation.data.store(DESTINATION, (760.0, -400.0))
        rotation.data.update_attribute(DESTINATION.name)
        assert rotation.data.read(DESTINATION) != (760.0, -400.0)
        assert PORTALS.platform_at(rotation.data.read(DESTINATION)) == UPPER
        assert rotation.data.read(DESTINATION_PLATFORM) == UPPER


def test_from_where_both_floors_are_reached_both_are_drawn() -> None:
    random.seed(3)
    rotation = _rotation(lambda: _fused(150.0, 0.0))
    drawn = set()
    for _ in range(40):
        rotation.data.store(DESTINATION, (160.0, 0.0))
        rotation.data.update_attribute(DESTINATION.name)
        drawn.add(PORTALS.platform_at(rotation.data.read(DESTINATION)))

    assert drawn == {LOWER, UPPER}


def test_the_destinations_logs_stay_in_the_movement_bucket() -> None:
    """Where `_rotation_mixins`, which drew the targets before #441, logs them."""
    assert bucket_for(destination_module.logger.name) == "movement"


def test_arrival_is_ten_minimap_px_in_virtual_px() -> None:
    assert RandomSource.ARRIVAL == 10 * 16
    assert SmartSource.ARRIVAL == 4 * 16


def test_abandon_draws_only_where_a_path_reaches() -> None:
    random.seed(4)
    rotation = _rotation(lambda: _fused(750.0, -400.0))

    targets = [rotation.provider.abandon() for _ in range(20)]

    assert {PORTALS.platform_at(t) for t in targets if t is not None} == {UPPER}
    assert rotation.data.read(DESTINATION) == targets[-1]


def test_abandon_does_nothing_while_the_destination_is_claimed() -> None:
    rotation = _rotation(lambda: _fused(750.0, -400.0))
    rotation.data.claim(
        DESTINATION, lambda _: (800.0, -400.0), holder="Claimant(T)", reason="test"
    )

    assert rotation.provider.abandon() is None
    assert rotation.data.read(DESTINATION) == (800.0, -400.0)


def test_no_position_is_read_on_a_map_with_no_minimap() -> None:
    """
    Movement recovery reads no position there: a read could only fail into the
    minimap's error handler.
    """
    reads: list[int] = []
    data = BotData("T")
    data.provide(
        WORLD_MAP,
        object.__new__(MapProvider),
        lambda: WorldMap(**{**_fields(PORTALS), "minimap": None}),
    )
    data.provide(
        POSITION,
        object.__new__(MinimapProvider),
        lambda: reads.append(1) or _fused(0.0, 0.0),
    )
    reads.clear()
    holder = SimpleNamespace(data=data, read=data.read)
    recovery = MovementRecovery(holder, physics=lambda: corpus.LAB_PHYSICS)  # pyright: ignore[reportArgumentType] - a holder that only reads

    reading = recovery._position()

    assert reading.value is None
    assert reads == []


def _fields(world: WorldMap) -> dict[str, object]:
    return {name: getattr(world, name) for name in world.__dataclass_fields__}


# --- the mob-spawn check's wander ----------------------------------------------


def test_a_wander_claim_wanders_the_platforms_whatever_the_mode() -> None:
    """
    No feature cycle on a `game_data` map: claimed with `wander`, as
    `CheckMobsStillSpawn` claims it while no mob shows, the destination is a
    random point on the platforms, a new one each time one is reached, even
    with smart rotation on.
    """
    data = _data()
    provider = destination(
        PORTALS,
        lambda: _fused(150.0, 0.0),
        data=data,
        game_physics=corpus.LAB_PHYSICS_VALUES,
        smart_rotation_enabled=True,
        mob_count_threshold=2,
    )
    emitted: list[str] = []
    provider.emit = lambda event_type, payload=None: emitted.append(event_type)  # type: ignore[method-assign]

    data.claim(DESTINATION, wander, holder="CheckMobsStillSpawn(T)", reason="test")
    emitted.clear()  # taking the Claim refreshed it once
    override(data, DESTINATION, value=(150.0, 0.0))  # reached, under the Claim
    data.update_attribute(DESTINATION.name)

    assert data.read(DESTINATION) != (150.0, 0.0)
    assert PORTALS.platform_at(data.read(DESTINATION)) is not None
    assert emitted == [MOVEMENT_TARGET_REACHED]


# --- the ladder check before a cast ------------------------------------------


def _hitting(
    world: WorldMap, at: Callable[[], Reading[VirtualPosition]]
) -> MobsHitting:
    """
    A `MobsHitting` on a Bot whose map is `world` and whose position is `at`'s,
    read once, as a Session has. `POSITION` is registered as `MinimapProvider`
    registers it, with no minimap to show.
    """
    data = BotData("T")
    providers = Providers(data, None, None, {})  # pyright: ignore[reportArgumentType] - nothing is sent
    providers.add(MapProvider, map_id=0, world_map=world)
    data.provide(POSITION, object.__new__(MinimapProvider), at, initial_value=at())
    data.update_attribute(POSITION.name)
    hitting = object.__new__(MobsHitting)
    hitting.data = data
    return hitting


@pytest.mark.parametrize(
    ("x", "y", "on_ladder"),
    [
        (300.0, -100.0, True),  # on `rope_grab`'s left rope
        (300.0, 0.0, False),  # on the floor under it
        (100.0, 0.0, False),
    ],
)
def test_no_skill_is_cast_on_a_rope_of_the_map(
    x: float, y: float, on_ladder: bool
) -> None:
    hitting = _hitting(WorldMap.from_map_data(rope_grab()), lambda: _fused(x, y))

    assert hitting._currently_on_ladder() is on_ladder


def test_an_unsure_position_is_not_on_a_ladder() -> None:
    unsure = Reading.unsure(0.0, "two characters")
    hitting = _hitting(WorldMap.from_map_data(rope_grab()), lambda: unsure)

    assert hitting._currently_on_ladder() is False


def test_the_ladder_check_reads_no_position() -> None:
    """The rotation reads it every cycle; a cast need not pay a camera match."""
    reads: list[int] = []
    hitting = _hitting(
        WorldMap.from_map_data(rope_grab()),
        lambda: reads.append(1) or _fused(300.0, -100.0),
    )
    override(hitting.data, POSITION, threshold=1e-9)
    reads.clear()

    assert hitting._currently_on_ladder() is True
    assert reads == []
