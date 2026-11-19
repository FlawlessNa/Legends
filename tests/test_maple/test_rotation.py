"""
`Rotation` on the framework (#442): what it declares, and the order a decision
takes its turn in: the recovery check, the gate, the destination and its
Movement Plan, then the send or the gate left.

A decision runs against its keys, served as their Providers serve them, and
stand-ins for its gate, its recovery and its pathing: no game client, no
Manager, no Main Process.
"""

import asyncio
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest

from botting import controller
from botting.core import (
    ActionRequest,
    BotData,
    DecisionMaker,
    WindowProvider,
    action_name,
)
from botting.core.data_keys import resolve_providers
from botting.core.supervisor import resolve_cancels
from botting.screen import Reading
from maple.decision_makers.providers import (
    DESTINATION,
    HANDLE,
    MOVEMENTS,
    POSITION,
    WORLD_MAP,
    DestinationProvider,
    MapProvider,
    MinimapProvider,
    PathingProvider,
)
from maple.decision_makers.recovery import MovementRecovery
from maple.decision_makers.rotation import Rotation
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from maple.telemetry_events import MOVEMENT_PLAN_STARTED
from tests.test_maple.movement_lab.fixture_maps import walk_corridor

IGN = "Tester"
WORLD = WorldMap.from_map_data(walk_corridor())
PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 80),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)
SENTINEL = (_MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),)


# --- what it declares -----------------------------------------------------------


def test_it_has_no_mixin_in_its_class_hierarchy() -> None:
    assert not [c for c in Rotation.__mro__ if c.__name__.endswith("Mixin")]


def test_it_reads_every_key_its_recovery_reads() -> None:
    assert set(MovementRecovery.reads) <= set(Rotation.reads)


def test_a_recovery_rung_preempts_its_own_movement() -> None:
    assert resolve_cancels([Rotation])[Rotation] == {Rotation}


def test_assembly_builds_its_destination_and_its_pathing() -> None:
    built = resolve_providers([Rotation])

    assert built.index(MinimapProvider) < built.index(DestinationProvider)
    assert built.index(DestinationProvider) < built.index(PathingProvider)


# --- a decision -----------------------------------------------------------------


class _Gate:
    """Records the turns a decision takes, in `log`, as the real gate is used."""

    def __init__(self, log: list[str], *, free: bool = True) -> None:
        self.log = log
        self.free = free

    def try_enter(self) -> bool:
        self.log.append("enter")
        return self.free

    def leave_now(self) -> None:
        self.log.append("leave")

    def releaser(self) -> None:
        self.log.append("released")


def _rotation(
    log: list[str], *, plan: tuple[_MovementComponent, ...] = PLAN, free: bool = True
) -> Rotation:
    """A `Rotation` past `setup()`, whose keys log their refresh."""
    data = BotData(IGN)
    here = Reading.read(VirtualPosition(50.0, 0.0, PositionSource.FUSED), 0.0)
    data.provide(HANDLE, object.__new__(WindowProvider), lambda: 7)
    data.provide(WORLD_MAP, object.__new__(MapProvider), lambda: WORLD)
    data.provide(POSITION, object.__new__(MinimapProvider), lambda: here)
    data.provide(
        DESTINATION,
        object.__new__(DestinationProvider),
        lambda: log.append("destination") or (100.0, 0.0),
    )
    data.provide(
        MOVEMENTS,
        object.__new__(PathingProvider),
        lambda: log.append("movements") or plan,
        threshold=0.1,
    )
    log.clear()
    rotation: Any = object.__new__(Rotation)
    DecisionMaker.__init__(rotation, {}, data, None)  # pyright: ignore[reportArgumentType] - nothing is piped
    rotation.gate = _Gate(log, free=free)
    rotation._recovery = SimpleNamespace(
        check=lambda now: log.append("check"), delivered=lambda count: None
    )
    rotation._pathing = SimpleNamespace(
        compiler=lambda correlation_id: ("compiled for", correlation_id)
    )
    rotation.sent = []

    def send(request: ActionRequest, correlation_id: str | None = None) -> None:
        log.append("send")
        rotation.sent.append(request)

    def emit(event_type: str, payload: Mapping[str, object] | None = None) -> None:
        log.append(event_type)

    rotation.send = send
    rotation.emit = emit
    return rotation


def _decide(rotation: Rotation) -> None:
    rotation.correlation_id = "decision"
    asyncio.run(rotation._decide())


def test_a_decision_checks_recovery_enters_refreshes_then_sends() -> None:
    log: list[str] = []
    rotation = _rotation(log)

    _decide(rotation)

    assert log == [
        "check",
        "enter",
        "destination",
        "movements",
        MOVEMENT_PLAN_STARTED,
        "send",
    ]


def test_a_decision_with_nothing_to_send_leaves_the_gate_itself() -> None:
    log: list[str] = []
    rotation = _rotation(log, plan=SENTINEL)

    _decide(rotation)

    assert log == ["check", "enter", "destination", "movements", "leave"]


def test_a_decision_off_its_turn_only_checks_recovery() -> None:
    """The gate is held by the Movement Action in flight: nothing is refreshed."""
    log: list[str] = []
    rotation = _rotation(log, free=False)

    _decide(rotation)

    assert log == ["check", "enter"]


def test_the_movement_action_leaves_the_gate_from_main_process() -> None:
    log: list[str] = []
    rotation: Any = _rotation(log)

    _decide(rotation)

    (request,) = rotation.sent
    assert request.identifier == action_name(Rotation, IGN)
    assert request.procedure is controller.compile_and_send
    assert request.requeue_if_not_scheduled is False
    assert request.callbacks == [rotation.gate.releaser]
    assert request.result_callbacks == [rotation._recovery.delivered]
    assert request.args == (7, ("compiled for", "decision"))


def test_on_start_restarts_the_grace_period_and_leaves_the_gate_alone() -> None:
    """Its `task()` override did only that: it never freed the lock."""
    log: list[str] = []
    rotation: Any = _rotation(log)
    rotation._recovery = SimpleNamespace(
        restart_grace_period=lambda: log.append("grace")
    )

    rotation.on_start()

    assert log == ["grace"]


@pytest.mark.parametrize("setting", ["movements_duration", "disable_teleport"])
def test_the_pathing_settings_configure_the_provider_not_the_rotation(
    setting: str,
) -> None:
    """`Rotation.__init__` took them; `PathingProvider` does now."""
    import inspect

    assert setting in inspect.signature(PathingProvider.__init__).parameters
    assert setting not in inspect.signature(Rotation.__init__).parameters
