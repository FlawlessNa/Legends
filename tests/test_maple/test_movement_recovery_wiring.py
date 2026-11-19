"""
The thin half of movement recovery: `MovementRecovery`, the helper `Rotation`
holds.

Every judgement is `StuckMonitor`'s and is checked in `test_movement_recovery.py`.
What is checked here is the plumbing that judgement is worthless without - reading
the loop's state from the Bot's keys, measuring the Delivery Gate across the process
boundary, and turning a `Reaction` into the right `ActionRequest`. This is the half
issue #128 could get wrong without a single detector misbehaving.

Everything is faked at the `BotData` level; no game client is involved, and the
manager proxy is a plain `queue.Queue`, which is the same interface the real one
presents. Its holder is a `Rotation` built without its Session, which records
what it sends, emits and pauses.
"""

import queue
import threading
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from botting.core import ActionRequest, BotData, ProxyFactory, TurnGate, action_name
from botting.screen import Reading
from maple.decision_makers.providers import (
    DESTINATION,
    MINIMAP_SHOWN,
    MOVEMENTS,
    PATH,
    POSITION,
    DestinationProvider,
    MinimapProvider,
    PathingProvider,
)
from maple.decision_makers.recovery import MovementRecovery, escalation_classes
from maple.decision_makers.rotation import Rotation
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.model.navigation import Direction, Move, MoveKind, Path, Point
from maple.model.world import WorldMap
from maple.movement_recovery import Reaction, RecoveryThresholds, Rung, Symptom
from maple.screen.position import PositionSource, VirtualPosition
from maple.telemetry_events import RECOVERY_STUCK_DETECTED
from tests.test_maple.movement_lab.corpus import LAB_PHYSICS
from tests.test_maple.movement_lab.fixture_maps import walk_corridor
from tests.test_maple.serving import destination, override

WALK = (_MovementComponent(MovementTypes.WALK_RIGHT, 80),)
SENTINEL_ONLY = (_MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),)

#: A map whose minimap transform is centre (1000, 1000), `mag` 4.
WORLD = WorldMap.from_map_data(walk_corridor())

#: A Path of one walk along the corridor's floor, lasting 0.4 s.
PATH_ = Path(
    (
        Move(
            MoveKind.WALK,
            Direction.RIGHT,
            (50.0, 0.0),
            (100.0, 0.0),
            WORLD.platforms[0],
            WORLD.platforms[0],
            0.4,
        ),
    )
)

#: Where the character stands: on the corridor's floor.
HERE = Reading.read(VirtualPosition(50.0, 0.0, PositionSource.FUSED), 0.0)


class _Proxies(ProxyFactory):
    """
    Stands in for ProxyFactory. A real subclass rather than a structural
    look-alike, because the helper's `setup` takes a `ProxyFactory` nominally -
    the same reason issue #105's fake `BotData` had to become a real one.
    """

    def __init__(self) -> None:
        super().__init__({})  # pyright: ignore[reportArgumentType]

    def instance(
        self, owner: str, primitive_type: str, *args: object, **kwargs: object
    ) -> queue.Queue:
        assert primitive_type == "Queue"
        return queue.Queue()


class _Loop:
    """
    The rotation's half of the wiring: a `Rotation` built without its Session,
    whose sends, records and Pauses are kept, and the helper it holds.
    """

    def __init__(self, data: BotData) -> None:
        self.data = data
        self.sent: list[ActionRequest] = []
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        self.paused: list[type] = []
        #: The Movement Plan `MOVEMENTS` serves.
        self.plan: tuple[_MovementComponent, ...] = WALK
        rotation: Any = Rotation.__new__(Rotation)
        rotation.data = data
        rotation.correlation_id = None
        rotation.send = lambda request, correlation_id=None: self.sent.append(request)
        rotation.emit = lambda event_type, payload=None, correlation_id=None: (
            self.emitted.append((event_type, payload or {}))
        )
        rotation.pause_for_user = lambda *classes, reason: self.paused.extend(classes)
        self.rotation: Rotation = rotation
        self.recovery = MovementRecovery(rotation, physics=lambda: LAB_PHYSICS)
        self.recovery.setup(_Proxies(), escalation_classes())


@pytest.fixture
def data() -> BotData:
    """
    The Bot's data, with `DESTINATION`'s Provider built as assembly builds it,
    and the Path, the Movement Plan and whether the minimap is shown served as
    their Providers serve them.
    """
    data = BotData("TestBot")
    destination(
        WORLD,
        lambda: HERE,
        data=data,
        handle=1234,
        frame=lambda: SimpleNamespace(pixels=None),
    )
    data.provide(PATH, object.__new__(PathingProvider), lambda: PATH_)
    data.provide(MINIMAP_SHOWN, object.__new__(MinimapProvider), lambda: True)
    return data


@pytest.fixture
def loop(data: BotData, mocker: MockerFixture) -> _Loop:
    mocker.patch(
        "maple.decision_makers.recovery.controller.key_binds",
        return_value={"jump": "space"},
    )
    made = _Loop(data)
    # Read at every read, as its 0.1 s threshold does at the decision interval:
    # a test changes the plan between two cycles.
    data.provide(
        MOVEMENTS, object.__new__(PathingProvider), lambda: made.plan, threshold=1e-9
    )
    return made


def _react(loop: _Loop, rung: Rung | None, **kwargs: object) -> Reaction:
    reaction = Reaction(Symptom.STALL, rung, (99, 99), **kwargs)  # pyright: ignore[reportArgumentType]
    loop.recovery._react_to(reaction)
    return reaction


# --- the Delivery Gate, across the process boundary --------------------------


def test_delivered_steps_are_summed_across_every_action_that_completed(
    loop: _Loop,
) -> None:
    """
    More than one Action can complete between two decision cycles, and the gate
    asks how many Steps landed in the window - not how many the last one did.
    """
    for count in (3, 5, 1):
        loop.recovery.delivered(count)

    assert loop.recovery._drain_delivery() == 9


def test_draining_empties_the_queue_so_a_window_is_counted_once(loop: _Loop) -> None:
    loop.recovery.delivered(4)
    assert loop.recovery._drain_delivery() == 4

    assert loop.recovery._drain_delivery() == 0


def test_the_movement_action_reports_its_delivered_prefix(loop: _Loop) -> None:
    """
    The wiring that makes the gate measurable at all: `compile_and_send` returns
    the Step count, and `result_callbacks` is what carries it back to the Engine.
    Without this the gate reads zero forever and no detector can ever fire.
    """
    rotation: Any = loop.rotation
    # What `setup()` gives it, short of a live proxy and a planning Provider:
    # what is under test is the wiring `Rotation` puts on its own Action.
    rotation.gate = TurnGate(threading.Lock())
    rotation._recovery = loop.recovery
    rotation._pathing = SimpleNamespace(compiler=lambda correlation_id: None)

    request = loop.rotation._request()
    for report in request.result_callbacks:
        report(5)

    assert loop.recovery._drain_delivery() == 5


# --- what the monitor is actually fed ----------------------------------------


def test_the_position_target_and_remaining_path_time_are_handed_over_in_virtual_px(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """#398: no canvas px on the way in, and the graph Path's time, not its nodes."""
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery._recovery_starts_at = 0.0

    loop.recovery.check(now=100.0)

    assert observe.call_args.args[0] == (50.0, 0.0)
    assert observe.call_args.kwargs["target"] == loop.data.read(DESTINATION)
    assert observe.call_args.kwargs["remaining"] == pytest.approx(0.4)


def test_an_unsure_position_is_handed_over_as_no_position(
    loop: _Loop, mocker: MockerFixture
) -> None:
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery._recovery_starts_at = 0.0
    override(
        loop.data, POSITION, update_function=lambda: Reading.unsure(0.0, "two there")
    )
    loop.data.update_attribute(POSITION.name)

    loop.recovery.check(now=100.0)

    assert observe.call_args.args[0] is None


def test_no_path_is_handed_over_as_no_remaining_time(
    loop: _Loop, mocker: MockerFixture
) -> None:
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery._recovery_starts_at = 0.0
    override(loop.data, PATH, update_function=lambda: None)
    loop.data.update_attribute("path")

    loop.recovery.check(now=100.0)

    assert observe.call_args.kwargs["remaining"] is None


def test_the_monitor_records_the_target_in_canvas_px_beside_virtual_px(
    loop: _Loop,
) -> None:
    """The map's minimap transform is handed to the monitor for the old fields."""
    loop.recovery._monitor.thresholds = RecoveryThresholds(stall_window=0.5)
    for now in (0.0, 1.0):
        loop.recovery._monitor.observe(
            (50.0, 0.0),
            now,
            target=(-976.0, -880.0),
            remaining=1.0,
            plan=WALK,
            delivered_steps=1,
        )

    (stuck,) = [p for e, p in loop.emitted if e == RECOVERY_STUCK_DETECTED]
    # `canvas * 16 - 1000 + 8`, the marker 6 rows up: canvas (1, 1).
    assert (stuck["target_x"], stuck["target_y"]) == (1, 1)
    assert (stuck["target_vx"], stuck["target_vy"]) == (-976.0, -880.0)


def test_a_sentinel_only_plan_is_handed_over_as_no_plan(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A plan holding nothing but END_OF_MOVEMENT compiles to no Input Sequence and
    is never dispatched. Reporting it as a plan would tell the gate the loop is
    planning when it is not - and would put Starvation in front of the Stall that
    an unplannable loop actually has.
    """
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery._recovery_starts_at = 0.0
    loop.plan = SENTINEL_ONLY

    loop.recovery.check(now=100.0)

    assert observe.call_args.kwargs["plan"] == ()


def test_a_stale_position_reading_is_reported_as_invalid(
    loop: _Loop, mocker: MockerFixture
) -> None:
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery._recovery_starts_at = 0.0
    # Patched on the class: `BotData.__setattr__` refuses anything that is not a
    # registered attribute, instance patching included.
    mocker.patch.object(
        BotData,
        "get_time_since_last_valid_update",
        return_value=loop.recovery.STALE_POSITION_AFTER + 1,
    )

    loop.recovery.check(now=100.0)

    assert observe.call_args.kwargs["position_valid"] is False


# --- the grace period ---------------------------------------------------------


def test_the_detectors_do_not_judge_the_first_seconds(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A Session's first cycles are spent finding the character and the minimap. A
    Stall measured through that is measuring the setup.
    """
    observe = mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)

    loop.recovery.check(now=0.0)

    observe.assert_not_called()


def test_the_grace_period_still_drains_what_was_delivered(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    Otherwise the backlog lands on the first judged cycle as one enormous window.
    """
    mocker.patch.object(loop.recovery._monitor, "observe", return_value=None)
    loop.recovery.delivered(6)

    loop.recovery.check(now=0.0)

    assert loop.recovery._drain_delivery() == 0


def test_a_resumed_loop_gets_its_grace_period_back(loop: _Loop) -> None:
    """
    A DecisionMaker that was suspended and resumed is where a fresh Session is:
    the character may be anywhere, and the first cycles find it again.
    """
    loop.recovery._recovery_starts_at = 0.0

    loop.recovery.restart_grace_period()

    assert loop.recovery._recovery_starts_at > 0.0


# --- Reflex --------------------------------------------------------------------


def test_reflex_preempts_the_rotation_action_it_is_unsticking(loop: _Loop) -> None:
    _react(loop, Rung.REFLEX, reflex_attempt=1)

    request = loop.sent.pop()
    assert request.cancel_tasks == [action_name(Rotation, "TestBot")]
    assert request.cancel_tasks == [repr(loop.rotation)]
    assert request.cancels_itself
    assert request.block_lower_priority


def test_the_reflex_jump_lasts_the_flight_of_the_current_jump(loop: _Loop) -> None:
    """No fixed hold (#396): a level jump's flight, from the current physics."""
    _react(loop, Rung.REFLEX, reflex_attempt=1)

    request = loop.sent.pop()
    assert request.args[2] == LAB_PHYSICS.jump_duration == 2 * 555 / 2000


def test_reflex_releases_through_the_ledger_rather_than_blind(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A latched direction key is the commonest cause of a Stall, and
    `release_directions` reads the Held-Keys Ledger - so it sends nothing for a
    key that is not down and cannot emit a phantom release (**A6**).
    """
    release = mocker.patch(
        "maple.decision_makers.recovery.controller.release_directions"
    )
    jump = mocker.patch(
        "maple.decision_makers.recovery.random_jump",
        return_value=mocker.Mock(send=mocker.AsyncMock()),
    )
    mocker.patch(
        "maple.decision_makers.recovery.asyncio.sleep",
        mocker.AsyncMock(),
    )
    import asyncio

    asyncio.run(loop.recovery._wait_and_random_jump(1234, "space", 0.555))

    release.assert_called_once_with(1234)
    jump.assert_called_once_with(1234, "space", 0.555)


# --- Abandon --------------------------------------------------------------------


def test_abandon_actually_changes_where_the_loop_is_heading(loop: _Loop) -> None:
    before = loop.data.read(DESTINATION)

    _react(loop, Rung.ABANDON, abandon_count=1)

    assert loop.data.read(DESTINATION) != before


def test_abandon_heads_for_a_point_on_a_platform(loop: _Loop) -> None:
    """
    The target update returns the *current* target until the character is within
    threshold of it, which is exactly what keeps a Stuck loop stuck: re-deciding
    cannot change where it is going. Abandon draws a new one on the platforms,
    through `DESTINATION`'s Provider.
    """
    first = loop.recovery._abandon_destination()
    second = loop.recovery._abandon_destination()
    assert first is not None
    assert second is not None

    assert first != second
    assert WORLD.platform_at(first) is not None
    assert WORLD.platform_at(second) is not None


def test_abandon_does_nothing_while_the_destination_is_claimed(loop: _Loop) -> None:
    """Its holder decides where the character goes: no new target, no alert."""
    claim = loop.data.claim(
        DESTINATION, lambda _: (60.0, 0.0), holder="X(TestBot)", reason="test"
    )

    _react(loop, Rung.ABANDON, abandon_count=1)

    assert loop.data.read(DESTINATION) == (60.0, 0.0)
    assert loop.sent == []
    loop.data.release(claim)


def _served_source_abandons(
    loop: _Loop, monkeypatch: pytest.MonkeyPatch
) -> list[Point]:
    """
    Stands in for the served source's `abandon()`: it heads for `ELSEWHERE`, and
    each call is kept.
    """
    providers = loop.data.providers
    assert providers is not None
    source = providers.get(DestinationProvider).source
    given: list[Point] = []
    monkeypatch.setattr(source, "abandon", lambda: given.append(ELSEWHERE) or ELSEWHERE)
    return given


#: Where the stand-in source's Abandon heads: the corridor's far end.
ELSEWHERE = (600.0, -20.0)


def test_abandon_heads_where_the_served_source_abandons_to(
    loop: _Loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each rotation's source picks its own Abandon (#577)."""
    given = _served_source_abandons(loop, monkeypatch)

    _react(loop, Rung.ABANDON, abandon_count=1)

    assert given == [ELSEWHERE]
    assert loop.data.read(DESTINATION) == ELSEWHERE


def test_abandon_asks_the_source_nothing_while_the_destination_is_claimed(
    loop: _Loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    given = _served_source_abandons(loop, monkeypatch)
    claim = loop.data.claim(
        DESTINATION, lambda _: (60.0, 0.0), holder="X(TestBot)", reason="test"
    )

    _react(loop, Rung.ABANDON, abandon_count=1)

    assert given == []
    assert loop.data.read(DESTINATION) == (60.0, 0.0)
    loop.data.release(claim)


def test_abandon_alerts_every_time(loop: _Loop) -> None:
    """
    Early spam is signal; rate-limiting waits until real session data justifies
    it (#119).
    """
    for _ in range(3):
        _react(loop, Rung.ABANDON, abandon_count=1)

    assert all(request.discord_request is not None for request in loop.sent)


def test_the_abandon_alert_names_the_suspected_connection(loop: _Loop) -> None:
    from maple.movement_recovery import SuspectedConnection

    _react(
        loop,
        Rung.ABANDON,
        abandon_count=1,
        suspected_connection=SuspectedConnection((1, 1), (4, 4), "JUMP"),
    )

    alert = loop.sent.pop().discord_request
    assert alert is not None
    assert "JUMP" in alert.msg


# --- Escalate --------------------------------------------------------------------


def test_escalate_suspends_the_loop_and_drops_the_keys(loop: _Loop) -> None:
    _react(loop, Rung.ESCALATE)

    assert Rotation in loop.paused
    request = loop.sent.pop()
    assert request.discord_request is not None
    assert request.procedure is loop.recovery._release_movement_keys
    assert request.cancel_tasks == [repr(loop.rotation)]


def test_escalate_pauses_for_the_user_what_it_disabled_before(loop: _Loop) -> None:
    """
    The classes the legacy disable named, as `CheckStillInMap` stops them, and
    the telecast: until Discord `RESUME` (ADR 0004).
    """
    _react(loop, Rung.ESCALATE)

    assert [cls.__name__ for cls in loop.paused] == [
        "Rotation",
        "CheckStillInMap",
        "CheckMobsStillSpawn",
        "MobsHitting",
        "TelecastMobsHitting",
    ]


def test_the_rotation_declares_what_an_escalate_pauses() -> None:
    from botting.core.supervisor import resolve_pauses

    assert resolve_pauses([Rotation])[Rotation] == set(escalation_classes())


def test_escalate_is_idempotent(loop: _Loop) -> None:
    """
    The disable cancels the loop only at its next `await`, so a caller can
    reach here again first - and each call would otherwise ship another alert
    and another key-release Action.
    """
    for _ in range(4):
        _react(loop, Rung.ESCALATE)

    assert len(loop.sent) == 1


def test_the_escalate_alert_tells_the_human_how_to_resume(loop: _Loop) -> None:
    _react(loop, Rung.ESCALATE)

    alert = loop.sent.pop().discord_request
    assert alert is not None
    assert "RESUME" in alert.msg


# --- Starvation -------------------------------------------------------------------


def test_starvation_alerts_without_touching_the_game(loop: _Loop) -> None:
    """
    Nothing about the map is wrong, so there is no rung: a Reflex would be noise
    and an Abandon would be a lie.
    """
    loop.recovery._react_to(Reaction(Symptom.STARVATION, None, (99, 99)))

    request = loop.sent.pop()
    assert request.discord_request is not None
    assert request.procedure is loop.recovery._noop
    assert loop.paused == []


# --- the Unsure position (#398) ---------------------------------------------------


def test_a_long_unsure_position_alerts_and_sends_no_key(loop: _Loop) -> None:
    """
    The rotation holds on purpose (C-NOGUESS), so the alert is all there is: a
    Reflex would move a character the bot can't place.
    """
    override(
        loop.data,
        POSITION,
        update_function=lambda: Reading.unsure(0.0, "2 characters within 32 px"),
    )
    loop.data.update_attribute(POSITION.name)

    loop.recovery._react_to(Reaction(Symptom.UNSURE_POSITION, None, (99, 99)))

    (request,) = loop.sent
    assert request.procedure is loop.recovery._noop
    assert request.discord_request is not None
    assert "2 characters within 32 px" in request.discord_request.msg
    assert "30 s" in request.discord_request.msg
    assert loop.paused == []


def test_a_long_unsure_streak_reaches_the_alert_through_the_cycle(
    loop: _Loop,
) -> None:
    """End to end: unsure reads, cycle after cycle, past the window, alert once."""
    override(
        loop.data,
        POSITION,
        update_function=lambda: Reading.unsure(0.0, "reads disagree"),
    )
    loop.data.update_attribute(POSITION.name)
    loop.recovery._recovery_starts_at = 0.0

    for second in range(40):
        loop.recovery.check(now=100.0 + second)

    alerts = [r.discord_request for r in loop.sent if r.discord_request is not None]
    assert len(alerts) == 1
    assert "reads disagree" in alerts[0].msg
