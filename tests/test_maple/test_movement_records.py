"""
Movement and state records (#340): `movement.plan_started`,
`movement.target_reached` and `state.snapshot`.

Everything is faked at the `BotData` level; no game client is involved. What
cannot be checked here is that the records appear on a real Session, at the
expected rates.
"""

import asyncio
import json
import math
import queue
import threading
import time
from collections.abc import Mapping
from types import SimpleNamespace
from typing import cast

import numpy as np

from botting.core import ActionRequest, BotData, TurnGate, WindowProvider
from botting.screen import Reading
from maple.decision_makers import StateSnapshot
from maple.decision_makers.providers import (
    DESTINATION,
    HANDLE,
    MOVEMENTS,
    ON_SCREEN_POSITION,
    POSITION,
    WORLD_MAP,
    DestinationProvider,
    MapProvider,
    MinimapProvider,
    OnScreenPositionProvider,
    PathingProvider,
)
from maple.decision_makers.recovery import MovementRecovery
from maple.decision_makers.rotation import Rotation
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition, marker_of_feet
from maple.telemetry_events import (
    MOVEMENT_PLAN_STARTED,
    MOVEMENT_TARGET_REACHED,
    STATE_SNAPSHOT,
    plan_started_payload,
    state_snapshot_payload,
    target_reached_payload,
)
from tests.test_maple.movement_lab.fixture_maps import walk_corridor
from tests.test_maple.serving import destination, override

#: A map whose minimap transform is centre (1000, 1000), `mag` 4.
WORLD = WorldMap.from_map_data(walk_corridor())

PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, cast("int", np.int64(80))),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)
#: A plan of nothing but the sentinel: nothing to send.
SENTINEL = (_MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),)

#: Where a marker at canvas px (3, 5) puts the feet on `WORLD`, and (20, 5):
#: `canvas * 16 - 1000 + 8`, the marker moved down its 6 rows.
FEET_AT_3_5 = (-944.0, -816.0)
FEET_AT_20_5 = (-672.0, -816.0)


def _fused(point: tuple[float, float]) -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(*point, PositionSource.FUSED), 0.0)


# --- payload builders ---------------------------------------------------------


_NO_POINTS = {
    "narrow": False,
    "edge_departure": False,
    "grabs_rope": False,
    "start": None,
    "end": None,
}


def test_plan_started_payload_is_json_primitives() -> None:
    payload = plan_started_payload(
        PLAN,
        (np.int64(3), np.int32(4)),
        (np.int64(10), np.int64(4)),
        virtual_position=(np.float64(-944.04), np.float64(-832.0)),
        virtual_target=(np.int64(-832), np.int64(-832)),
        scale=16,
    )

    assert payload == {
        "components": [["WALK_RIGHT", 5], ["END_OF_MOVEMENT", 1]],
        "components_v": [["WALK_RIGHT", 80.0], ["END_OF_MOVEMENT", 0.0]],
        "transitions": [_NO_POINTS, _NO_POINTS],
        "from_x": 3,
        "from_y": 4,
        "target_x": 10,
        "target_y": 4,
        "from_vx": -944.0,
        "from_vy": -832.0,
        "target_vx": -832.0,
        "target_vy": -832.0,
    }
    json.dumps(payload)  # raises on any numpy scalar
    assert type(payload["from_x"]) is int
    assert type(payload["components"][0][1]) is int
    assert type(payload["from_vx"]) is float


def test_plan_started_components_count_gestures_as_they_always_did() -> None:
    """
    `components` keeps its pre-#396 meaning, so an analyzer reads old and new
    Sessions alike: a walk or a climb in canvas px, a gesture as a count (1 per
    jump or portal, the casts for a teleport). `components_v` has every length.
    """
    plan = (
        _MovementComponent(MovementTypes.CLIMB_UP, 48.0),
        _MovementComponent(MovementTypes.JUMP_RIGHT, 69.4, duration=0.555),
        _MovementComponent(MovementTypes.TELEPORT_UP, 300.0, casts=2),
        _MovementComponent(MovementTypes.ENTER_PORTAL, 0.0, duration=0.128),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    payload = plan_started_payload(
        plan, (0, 0), (1, 1), virtual_position=(0, 0), virtual_target=(16, 16), scale=16
    )

    assert payload["components"] == [
        ["CLIMB_UP", 3],
        ["JUMP_RIGHT", 1],
        ["TELEPORT_UP", 2],
        ["ENTER_PORTAL", 1],
        ["END_OF_MOVEMENT", 1],
    ]
    assert [length for _, length in payload["components_v"]] == [
        48.0,
        69.4,
        300.0,
        0.0,
        0.0,
    ]


def test_target_reached_payload_carries_the_distance() -> None:
    payload = target_reached_payload((np.int64(3), np.int64(0)), (np.int64(0), 4))

    assert payload == {
        "target_x": 0,
        "target_y": 4,
        "distance": 5.0,
        "target_vx": None,
        "target_vy": None,
        "vx": None,
        "vy": None,
        "virtual_distance": None,
    }
    json.dumps(payload)
    assert type(payload["target_x"]) is int


def test_target_reached_payload_carries_the_virtual_distance_when_known() -> None:
    payload = target_reached_payload(
        (3, 0),
        (0, 4),
        virtual_position=(np.float64(100.0), np.float64(-20.0)),
        virtual_target=(106, -28),
    )

    assert payload["vx"] == 100.0
    assert payload["target_vy"] == -28.0
    assert payload["virtual_distance"] == 10.0
    json.dumps(payload)


def test_state_snapshot_payload_converts_numpy_and_centres_the_box() -> None:
    payload = state_snapshot_payload(
        (np.int64(1), np.int64(2)),
        (np.int64(3), np.int64(4)),
        np.array([10, 20, 30, 60]).tolist(),
    )

    assert payload == {
        "x": 1,
        "y": 2,
        "target_x": 3,
        "target_y": 4,
        "on_screen_x": 20,
        "on_screen_y": 40,
        "vx": None,
        "vy": None,
        "target_vx": None,
        "target_vy": None,
    }
    json.dumps(payload)


def test_state_snapshot_payload_carries_the_virtual_fields_beside() -> None:
    payload = state_snapshot_payload(
        (3, 5),
        (20, 5),
        None,
        virtual_position=(np.float64(-944.04), -816.0),
        virtual_target=FEET_AT_20_5,
    )

    assert (payload["vx"], payload["vy"]) == (-944.0, -816.0)
    assert (payload["target_vx"], payload["target_vy"]) == FEET_AT_20_5
    json.dumps(payload)


# --- StateSnapshot ------------------------------------------------------------


class _Proxies:
    def instance(self, *args: object, **kwargs: object) -> object:
        return queue.Queue()

    def shared(self, *args: object, **kwargs: object) -> object:
        return queue.Queue()


def _snapshot(data: BotData) -> list[tuple[str, Mapping[str, object]]]:
    emitted: list[tuple[str, Mapping[str, object]]] = []
    maker = StateSnapshot.__new__(StateSnapshot)
    maker.data = data
    maker.emit = lambda event_type, payload=None: emitted.append(  # pyright: ignore[reportAttributeAccessIssue]
        (event_type, payload or {})
    )
    asyncio.run(maker._decide())
    return emitted


def test_state_snapshot_is_throttled_to_one_second() -> None:
    assert StateSnapshot._throttle == 1.0


def test_state_snapshot_emits_nulls_when_nothing_is_known() -> None:
    ((event_type, payload),) = _snapshot(BotData("TestBot"))

    assert event_type == STATE_SNAPSHOT
    assert payload == {
        "x": None,
        "y": None,
        "target_x": None,
        "target_y": None,
        "on_screen_x": None,
        "on_screen_y": None,
        "vx": None,
        "vy": None,
        "target_vx": None,
        "target_vy": None,
    }


def test_state_snapshot_reads_the_cache_without_updating() -> None:
    """
    The virtual position and target, and their canvas px as the minimap draws
    the marker for each (#398): `current_minimap_position` is gone.
    """
    calls: list[str] = []
    data = BotData("TestBot")
    data.provide(WORLD_MAP, object.__new__(MapProvider), lambda: WORLD)
    data.provide(
        POSITION,
        object.__new__(MinimapProvider),
        lambda: calls.append("pos") or _fused(FEET_AT_3_5),
    )
    data.provide(
        DESTINATION,
        object.__new__(DestinationProvider),
        lambda: calls.append("target") or FEET_AT_20_5,
    )
    data.provide(
        ON_SCREEN_POSITION,
        object.__new__(OnScreenPositionProvider),
        lambda: calls.append("screen") or (0, 0, 2, 2),
    )
    calls.clear()

    ((_, payload),) = _snapshot(data)

    assert calls == []
    assert (payload["x"], payload["y"]) == (3, 5)
    assert (payload["vx"], payload["vy"]) == FEET_AT_3_5
    assert (payload["target_x"], payload["target_y"]) == (20, 5)
    assert (payload["target_vx"], payload["target_vy"]) == FEET_AT_20_5
    assert payload["on_screen_x"] == 1


def test_state_snapshot_of_an_unsure_position_has_no_position() -> None:
    data = BotData("TestBot")
    data.provide(WORLD_MAP, object.__new__(MapProvider), lambda: WORLD)
    data.provide(
        POSITION,
        object.__new__(MinimapProvider),
        lambda: Reading.unsure(0.0, "two"),
    )

    ((_, payload),) = _snapshot(data)

    assert payload["x"] is None
    assert payload["vx"] is None


# --- Rotation -----------------------------------------------------------------


_COMPILER = object()


class _Loop(Rotation):
    """
    A `Rotation` built without its Session: it reads the Bot's keys, served as
    their Providers serve them, enters a gate that is always free, and keeps
    what it sends and records.
    """

    def __init__(self, emit_works: bool) -> None:  # pyright: ignore[reportMissingSuperCall] - no Session
        data = BotData("TestBot")
        data.provide(HANDLE, object.__new__(WindowProvider), lambda: 1234)
        data.provide(WORLD_MAP, object.__new__(MapProvider), lambda: WORLD)
        data.provide(
            DESTINATION, object.__new__(DestinationProvider), lambda: FEET_AT_20_5
        )
        data.provide(MOVEMENTS, object.__new__(PathingProvider), lambda: PLAN)
        data.provide(
            POSITION, object.__new__(MinimapProvider), lambda: _fused(FEET_AT_3_5)
        )
        self.data = data
        self.correlation_id = None
        self.gate = TurnGate(threading.Lock())
        self._recovery = cast(
            MovementRecovery,
            SimpleNamespace(check=lambda now: None, delivered=queue.Queue().put_nowait),
        )
        self._pathing = cast(
            PathingProvider, SimpleNamespace(compiler=lambda correlation_id: _COMPILER)
        )
        self.sent: list[ActionRequest] = []
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        self.emit_works = emit_works

    def __repr__(self) -> str:
        return "Rotation(TestBot)"

    def send(self, request: ActionRequest, correlation_id: str | None = None) -> None:
        self.sent.append(request)

    def emit(
        self,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if self.emit_works:
            self.emitted.append((event_type, payload or {}))


def _decide(loop: _Loop) -> None:
    asyncio.run(loop._decide())


def test_rotation_emits_plan_started_before_sending() -> None:
    loop = _Loop(emit_works=True)
    order: list[str] = []
    send, emit = loop.send, loop.emit

    def sent(request: ActionRequest, correlation_id: str | None = None) -> None:
        order.append("send")
        send(request)

    def traced(event_type: str, payload: Mapping[str, object] | None = None) -> None:
        order.append("emit")
        emit(event_type, payload)

    loop.send = sent  # pyright: ignore[reportAttributeAccessIssue] - traced
    loop.emit = traced  # pyright: ignore[reportAttributeAccessIssue] - traced

    _decide(loop)

    assert order == ["emit", "send"]
    ((event_type, payload),) = loop.emitted
    assert event_type == MOVEMENT_PLAN_STARTED
    assert (payload["from_x"], payload["from_y"]) == (3, 5)
    assert (payload["target_x"], payload["target_y"]) == (20, 5)
    assert (payload["from_vx"], payload["from_vy"]) == FEET_AT_3_5
    assert (payload["target_vx"], payload["target_vy"]) == FEET_AT_20_5
    assert payload["components"] == [["WALK_RIGHT", 5], ["END_OF_MOVEMENT", 1]]
    assert payload["components_v"] == [["WALK_RIGHT", 80.0], ["END_OF_MOVEMENT", 0.0]]


def test_the_action_request_is_the_same_with_telemetry_on_or_off() -> None:
    on, off = _Loop(emit_works=True), _Loop(emit_works=False)

    _decide(on)
    _decide(off)

    (a,), (b,) = on.sent, off.sent
    assert a.procedure is b.procedure
    assert a.args[0] == b.args[0]
    assert a.args[1] is b.args[1]
    assert a.priority == b.priority
    assert a.requeue_if_not_scheduled == b.requeue_if_not_scheduled
    assert len(on.emitted) == 1


def test_plan_started_does_not_refresh_a_thresholded_attribute() -> None:
    """
    Reading `POSITION` past its threshold re-runs a position read.
    Telemetry on the send path must read the cache instead.
    """
    loop = _Loop(emit_works=True)
    reads: list[int] = []
    override(
        loop.data,
        POSITION,
        update_function=lambda: reads.append(1) or _fused(FEET_AT_3_5),
        threshold=0.001,
    )
    loop.data.update_attribute(POSITION.name)
    reads.clear()
    time.sleep(0.01)  # past the threshold: a plain read would now refresh

    _decide(loop)

    assert reads == []
    ((event_type, payload),) = loop.emitted
    assert event_type == MOVEMENT_PLAN_STARTED
    assert payload["from_x"] == 3


def test_plan_started_takes_both_targets_from_one_read() -> None:
    """
    The virtual target and its canvas equivalent come from the same cached
    read: a refresh between the two can't make them describe different targets.
    Here every read of `next_target` would give a new one, 16 px (a canvas
    pixel) further along each time.
    """
    loop = _Loop(emit_works=True)
    reads = iter(range(0, 320, 16))
    override(
        loop.data,
        DESTINATION,
        update_function=lambda: (FEET_AT_20_5[0] + next(reads), FEET_AT_20_5[1]),
        threshold=1e-9,
    )
    transform = WORLD.minimap
    assert transform is not None

    _decide(loop)

    ((_, payload),) = loop.emitted
    target_vx, target_vy = payload["target_vx"], payload["target_vy"]
    assert isinstance(target_vx, float)
    assert isinstance(target_vy, float)
    assert (payload["target_x"], payload["target_y"]) == marker_of_feet(
        transform, (target_vx, target_vy)
    )


def test_no_plan_started_when_there_is_nothing_to_send() -> None:
    loop = _Loop(emit_works=True)
    override(loop.data, MOVEMENTS, update_function=lambda: SENTINEL)

    _decide(loop)

    assert loop.emitted == []
    assert loop.sent == []


# --- target_reached -----------------------------------------------------------


#: The rotation's target in the arrival tests: on `WORLD`'s floor.
TARGET = (100.0, 0.0)


class _Owner:
    """`DestinationProvider`, which judges arrival, and what it emitted."""

    def __init__(self, provider: DestinationProvider) -> None:
        self.data = provider.data
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        provider.emit = lambda event_type, payload=None: self.emitted.append(  # type: ignore[method-assign]
            (event_type, payload or {})
        )


def _owner(position: tuple[float, float], *, smart: bool = False) -> _Owner:
    provider = destination(
        WORLD,
        lambda: _fused(position),
        smart_rotation_enabled=smart,
        mob_count_threshold=2 if smart else None,
    )
    owner = _Owner(provider)
    owner.data.store(DESTINATION, TARGET)
    return owner


def test_basic_rotation_emits_on_arrival_in_virtual_px() -> None:
    """
    Arrival is judged in virtual px since #398: within 160 px (10 minimap px). The
    canvas fields are where the minimap draws the marker for each.
    """
    owner = _owner((130.0, 0.0))
    transform = WORLD.minimap
    assert transform is not None

    owner.data.update_attribute(DESTINATION.name)

    ((event_type, payload),) = owner.emitted
    assert event_type == MOVEMENT_TARGET_REACHED
    here, there = (
        marker_of_feet(transform, (130.0, 0.0)),
        marker_of_feet(transform, TARGET),
    )
    assert payload == {
        "target_x": there[0],
        "target_y": there[1],
        "distance": math.dist(here, there),
        "target_vx": 100.0,
        "target_vy": 0.0,
        "vx": 130.0,
        "vy": 0.0,
        "virtual_distance": 30.0,
    }
    assert owner.data.read(DESTINATION) != TARGET
    assert WORLD.platform_at(owner.data.read(DESTINATION)) is not None


def test_basic_rotation_is_silent_while_travelling() -> None:
    owner = _owner((400.0, -20.0))

    owner.data.update_attribute(DESTINATION.name)

    assert owner.emitted == []
    assert owner.data.read(DESTINATION) == TARGET


def test_an_unsure_position_holds_the_target() -> None:
    """Arrival can't be judged from a position nobody placed."""
    owner = _owner((100.0, 0.0))
    override(owner.data, POSITION, update_function=lambda: Reading.unsure(0.0, "two"))
    owner.data.update_attribute(POSITION.name)

    owner.data.update_attribute(DESTINATION.name)

    assert owner.emitted == []
    assert owner.data.read(DESTINATION) == TARGET


def test_smart_rotation_emits_once_on_arrival() -> None:
    owner = _owner((110.0, 0.0), smart=True)

    owner.data.update_attribute(DESTINATION.name)
    owner.data.update_attribute(DESTINATION.name)  # still dwelling: no second record

    ((event_type, payload),) = owner.emitted
    assert event_type == MOVEMENT_TARGET_REACHED
    assert payload["virtual_distance"] == 10.0


def test_smart_rotation_is_silent_while_travelling() -> None:
    """Its arrival is 64 px (4 minimap px)."""
    owner = _owner((170.0, 0.0), smart=True)

    owner.data.update_attribute(DESTINATION.name)

    assert owner.emitted == []
