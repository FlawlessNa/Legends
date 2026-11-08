"""
Movement and state records (#340): `movement.plan_started`,
`movement.target_reached` and `state.snapshot`.

Everything is faked at the `BotData` level; no game client is involved. What
cannot be checked here is that the records appear on a real Session, at the
expected rates.
"""

import asyncio
import json
import queue
from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import cast

import numpy as np
import pytest

from botting.core import ActionRequest, BotData
from maple.decision_makers import StateSnapshot
from maple.decision_makers.mixins import NextTargetMixin
from maple.decision_makers.rotation import Rotation
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.telemetry_events import (
    MOVEMENT_PLAN_STARTED,
    MOVEMENT_TARGET_REACHED,
    STATE_SNAPSHOT,
    plan_started_payload,
    state_snapshot_payload,
    target_reached_payload,
)

PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, cast("int", np.int64(5))),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),
)


# --- payload builders ---------------------------------------------------------


def test_plan_started_payload_is_json_primitives() -> None:
    payload = plan_started_payload(
        PLAN, (np.int64(3), np.int32(4)), (np.int64(10), np.int64(4))
    )

    assert payload == {
        "components": [["WALK_RIGHT", 5], ["END_OF_MOVEMENT", 1]],
        "from_x": 3,
        "from_y": 4,
        "target_x": 10,
        "target_y": 4,
    }
    json.dumps(payload)  # raises on any numpy scalar
    assert type(payload["from_x"]) is int
    assert type(payload["components"][0][1]) is int


def test_target_reached_payload_carries_the_distance() -> None:
    payload = target_reached_payload((np.int64(3), np.int64(0)), (np.int64(0), 4))

    assert payload == {"target_x": 0, "target_y": 4, "distance": 5.0}
    json.dumps(payload)
    assert type(payload["target_x"]) is int


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
    }
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
    }


def test_state_snapshot_reads_the_cache_without_updating() -> None:
    calls: list[str] = []
    data = BotData("TestBot")
    data.create_attribute(
        "current_minimap_position", lambda: calls.append("pos") or (7, 8)
    )
    data.create_attribute("next_target", lambda: calls.append("target") or (1, 2))
    data.create_attribute(
        "current_on_screen_position", lambda: calls.append("screen") or (0, 0, 2, 2)
    )
    for name in (
        "current_minimap_position",
        "next_target",
        "current_on_screen_position",
    ):
        data.update_attribute(name)
    calls.clear()

    ((_, payload),) = _snapshot(data)

    assert calls == []
    assert payload["x"] == 7
    assert payload["target_x"] == 1
    assert payload["on_screen_x"] == 1


# --- Rotation -----------------------------------------------------------------


_COMPILER = object()


class _Loop:
    """Stands in for the Rotation DecisionMaker, as the recovery wiring tests do."""

    def __init__(self, emit_works: bool) -> None:
        data = BotData("TestBot")
        data.set_static("handle", 1234)
        data.create_attribute("next_target", lambda: (20, 5))
        data.create_attribute("movements", lambda: PLAN)
        data.create_attribute("current_minimap_position", lambda: (3, 5))
        self.data = data
        self.lock = SimpleNamespace(
            acquire=lambda blocking=False: True, release=lambda: None
        )
        self._delivery = queue.Queue()
        self.sent: list[ActionRequest] = []
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        self.send = self.sent.append
        self.emit = (
            (
                lambda event_type, payload=None: self.emitted.append(
                    (event_type, payload or {})
                )
            )
            if emit_works
            else (lambda event_type, payload=None: None)
        )
        self._recovery_check = lambda now: None
        self._has_movements: Callable[[], bool] = lambda: True
        self._compiler = _COMPILER
        self._movement_compiler = lambda: self._compiler

    def __repr__(self) -> str:
        return "Rotation(TestBot)"

    def _request(self) -> ActionRequest:
        return Rotation._request(self)  # pyright: ignore[reportArgumentType]


def _decide(loop: _Loop) -> None:
    asyncio.run(Rotation._decide(loop))  # pyright: ignore[reportArgumentType]


def test_rotation_emits_plan_started_before_sending() -> None:
    loop = _Loop(emit_works=True)
    order: list[str] = []
    loop.send = lambda request: order.append("send")
    emit = loop.emit

    def traced(event_type: str, payload: Mapping[str, object] | None = None) -> None:
        order.append("emit")
        emit(event_type, payload)

    loop.emit = traced

    _decide(loop)

    assert order == ["emit", "send"]
    ((event_type, payload),) = loop.emitted
    assert event_type == MOVEMENT_PLAN_STARTED
    assert payload["from_x"] == 3
    assert payload["target_x"] == 20
    assert payload["components"] == [["WALK_RIGHT", 5], ["END_OF_MOVEMENT", 1]]


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


def test_no_plan_started_when_there_is_nothing_to_send() -> None:
    loop = _Loop(emit_works=True)
    loop._has_movements = lambda: False

    _decide(loop)

    assert loop.emitted == []
    assert loop.sent == []


# --- target_reached -----------------------------------------------------------


class _Feature:
    def random(self) -> tuple[int, int]:
        return 50, 50


class _Minimap:
    def __init__(self, cycle: bool) -> None:
        self.feature_cycle = [_Feature()] if cycle else None

    def random_point(self) -> tuple[int, int]:
        return 50, 50

    def get_feature_containing(self, target: tuple[int, int]) -> _Feature:
        return _Feature()


class _Owner(NextTargetMixin):
    def __init__(self, data: BotData) -> None:
        self.data = data
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        self.emit = lambda event_type, payload=None: self.emitted.append(
            (event_type, payload or {})
        )
        self.get_mobs_positions_in_img = lambda *a, **k: []


def _owner(position: tuple[int, int], *, cycle: bool, smart: bool = False) -> _Owner:
    data = BotData("TestBot")
    data.set_static("current_minimap", _Minimap(cycle))
    data.set_static("current_minimap_position", position)
    owner = _Owner(data)
    owner._create_rotation_attributes(
        smart_rotation=smart, mob_count_threshold=2 if smart else None
    )
    data.next_target = (10, 10)
    return owner


@pytest.mark.parametrize("cycle", [True, False], ids=["cycle", "random"])
def test_basic_rotation_emits_on_arrival(cycle: bool) -> None:
    owner = _owner((10, 12), cycle=cycle)

    owner.data.update_attribute("next_target")

    ((event_type, payload),) = owner.emitted
    assert event_type == MOVEMENT_TARGET_REACHED
    assert payload == {"target_x": 10, "target_y": 10, "distance": 2.0}


@pytest.mark.parametrize("cycle", [True, False], ids=["cycle", "random"])
def test_basic_rotation_is_silent_while_travelling(cycle: bool) -> None:
    owner = _owner((100, 10), cycle=cycle)

    owner.data.update_attribute("next_target")

    assert owner.emitted == []


def test_smart_rotation_emits_once_on_arrival() -> None:
    owner = _owner((10, 11), cycle=True, smart=True)

    owner.data.update_attribute("next_target")
    owner.data.update_attribute("next_target")  # still dwelling: no second record

    ((event_type, payload),) = owner.emitted
    assert event_type == MOVEMENT_TARGET_REACHED
    assert payload["distance"] == 1.0


def test_smart_rotation_is_silent_while_travelling() -> None:
    owner = _owner((100, 10), cycle=True, smart=True)

    owner.data.update_attribute("next_target")

    assert owner.emitted == []
