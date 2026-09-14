"""
The thin half of movement recovery: `MovementRecoveryMixin`.

Every judgement is `StuckMonitor`'s and is checked in `test_movement_recovery.py`.
What is checked here is the plumbing that judgement is worthless without - reading
the loop's state out of `BotData`, measuring the Delivery Gate across the process
boundary, and turning a `Reaction` into the right `ActionRequest`. This is the half
issue #128 could get wrong without a single detector misbehaving.

Everything is faked at the `BotData` level; no game client is involved, and the
manager proxy is a plain `queue.Queue`, which is the same interface the real one
presents.
"""

import queue
from collections.abc import Callable, Mapping

import pytest
from pytest_mock import MockerFixture

from botting.core import ActionRequest, BotData, ProxyFactory
from maple.decision_makers.mixins import MovementRecoveryMixin, NextTargetMixin
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)
from maple.movement_recovery import Reaction, Rung, Symptom

WALK = (_MovementComponent(MovementTypes.WALK_RIGHT, 5),)
SENTINEL_ONLY = (_MovementComponent(MovementTypes.END_OF_MOVEMENT, 1),)


class _Node:
    def __init__(self, x: int, y: int) -> None:
        self.x, self.y = x, y


class _Feature:
    left, right, top = 0, 100, 5
    avoid_edges = False
    edge_threshold = 0

    def __init__(self, point: tuple[int, int]) -> None:
        self._point = point

    def random(self) -> tuple[int, int]:
        return self._point


class _Minimap:
    """The bare minimum the rotation and recovery mixins read off a minimap."""

    def __init__(self, *, cycle: bool = False) -> None:
        self.feature_cycle = [_Feature((10, 10)), _Feature((20, 20))] if cycle else None
        self.points = iter([(31, 31), (32, 32), (33, 33), (34, 34)])

    def random_point(self) -> tuple[int, int]:
        return next(self.points)

    def get_feature_containing(self, target: tuple[int, int]) -> _Feature:
        return _Feature(target)


class _Proxies(ProxyFactory):
    """
    Stands in for ProxyFactory. A real subclass rather than a structural
    look-alike, because the mixin declares `_proxies: ProxyFactory` nominally -
    the same reason issue #105's fake `BotData` had to become a real one.
    """

    def __init__(self) -> None:
        super().__init__({})  # pyright: ignore[reportArgumentType]

    def instance(
        self, owner: str, primitive_type: str, *args: object, **kwargs: object
    ) -> queue.Queue:
        assert primitive_type == "Queue"
        return queue.Queue()


class _Loop(MovementRecoveryMixin, NextTargetMixin):
    """Stands in for the Rotation DecisionMaker."""

    def __init__(self, data: BotData) -> None:
        self.data = data
        self._proxies = _Proxies()
        self.sent: list[ActionRequest] = []
        self.emitted: list[tuple[str, Mapping[str, object]]] = []
        self.disabled: list[str] = []
        self.plan: tuple[_MovementComponent, ...] = WALK
        # Assigned rather than overridden: the mixin declares each of these as a
        # `Callable` attribute, which is the mixin-typing idiom, and a method of
        # the same name in a subclass is a different thing to pyright.
        self.send = self.sent.append
        self.emit = lambda event_type, payload: self.emitted.append(
            (event_type, payload)
        )
        self._disable_decision_makers = lambda *names, self_only=False: (
            self.disabled.extend(names)
        )
        self._has_movements = lambda: len(self.plan) > 1
        # What `Rotation._request` reads besides the recovery wiring.
        self.lock: object = None
        self._movement_compiler: Callable[[], object] = lambda: None
        self._create_recovery_attributes()

    def __repr__(self) -> str:
        return f"Rotation({self.data.ign})"


@pytest.fixture
def data() -> BotData:
    data = BotData("TestBot")
    data.set_static("handle", 1234)
    data.set_static("current_minimap", _Minimap())
    data.set_static("current_client_img", None)
    data.create_attribute("current_minimap_position", lambda: (50, 50))
    data.create_attribute("path", lambda: (_Node(1, 1), _Node(2, 2)))
    data.create_attribute("minimap_currently_displayed", lambda: True)
    return data


@pytest.fixture
def loop(data: BotData, mocker: MockerFixture) -> _Loop:
    mocker.patch(
        "maple.decision_makers.mixins._recovery_mixins.controller.key_binds",
        return_value={"jump": "space"},
    )
    loop = _Loop(data)
    loop._create_rotation_attributes()
    return loop


def _react(loop: _Loop, rung: Rung | None, **kwargs: object) -> Reaction:
    reaction = Reaction(Symptom.STALL, rung, (99, 99), **kwargs)  # pyright: ignore[reportArgumentType]
    loop._react_to(reaction)
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
        loop._delivery.put_nowait(count)

    assert loop._drain_delivery() == 9


def test_draining_empties_the_queue_so_a_window_is_counted_once(loop: _Loop) -> None:
    loop._delivery.put_nowait(4)
    assert loop._drain_delivery() == 4

    assert loop._drain_delivery() == 0


def test_the_movement_action_reports_its_delivered_prefix(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    The wiring that makes the gate measurable at all: `compile_and_send` returns
    the Step count, and `result_callbacks` is what carries it back to the Engine.
    Without this the gate reads zero forever and no detector can ever fire.
    """
    from maple.decision_makers.rotation import Rotation

    loop.lock = mocker.Mock()
    loop._movement_compiler = lambda: None

    # `Rotation._request` is called unbound against the fake on purpose: what is
    # under test is the wiring `Rotation` puts on its own Action, and a real one
    # needs a live proxy, a pipe and a client. Issue #105 settled this shape.
    request = Rotation._request(loop)  # pyright: ignore[reportArgumentType]
    for report in request.result_callbacks:
        report(5)

    assert loop._drain_delivery() == 5


# --- what the monitor is actually fed ----------------------------------------


def test_the_path_is_handed_over_as_plain_coordinates(
    loop: _Loop, mocker: MockerFixture
) -> None:
    observe = mocker.patch.object(loop._monitor, "observe", return_value=None)
    loop._restart_recovery_grace_period()
    loop._recovery_starts_at = 0.0

    loop._recovery_check(now=100.0)

    assert observe.call_args.kwargs["path"] == ((1, 1), (2, 2))


def test_a_sentinel_only_plan_is_handed_over_as_no_plan(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A plan holding nothing but END_OF_MOVEMENT compiles to no Input Sequence and
    is never dispatched. Reporting it as a plan would tell the gate the loop is
    planning when it is not - and would put Starvation in front of the Stall that
    an unplannable loop actually has.
    """
    observe = mocker.patch.object(loop._monitor, "observe", return_value=None)
    loop._recovery_starts_at = 0.0
    loop.plan = SENTINEL_ONLY

    loop._recovery_check(now=100.0)

    assert observe.call_args.kwargs["plan"] == ()


def test_a_stale_position_reading_is_reported_as_invalid(
    loop: _Loop, mocker: MockerFixture
) -> None:
    observe = mocker.patch.object(loop._monitor, "observe", return_value=None)
    loop._recovery_starts_at = 0.0
    # Patched on the class: `BotData.__setattr__` refuses anything that is not a
    # registered attribute, instance patching included.
    mocker.patch.object(
        BotData,
        "get_time_since_last_valid_update",
        return_value=loop.STALE_POSITION_AFTER + 1,
    )

    loop._recovery_check(now=100.0)

    assert observe.call_args.kwargs["position_valid"] is False


# --- the grace period ---------------------------------------------------------


def test_the_detectors_do_not_judge_the_first_seconds(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A Session's first cycles are spent finding the character and the minimap. A
    Stall measured through that is measuring the setup.
    """
    observe = mocker.patch.object(loop._monitor, "observe", return_value=None)

    loop._recovery_check(now=0.0)

    observe.assert_not_called()


def test_the_grace_period_still_drains_what_was_delivered(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    Otherwise the backlog lands on the first judged cycle as one enormous window.
    """
    mocker.patch.object(loop._monitor, "observe", return_value=None)
    loop._delivery.put_nowait(6)

    loop._recovery_check(now=0.0)

    assert loop._drain_delivery() == 0


def test_a_resumed_loop_gets_its_grace_period_back(loop: _Loop) -> None:
    """
    A DecisionMaker that was suspended and resumed is where a fresh Session is:
    the character may be anywhere, and the first cycles find it again.
    """
    loop._recovery_starts_at = 0.0

    loop._restart_recovery_grace_period()

    assert loop._recovery_starts_at > 0.0


# --- Reflex --------------------------------------------------------------------


def test_reflex_preempts_the_rotation_action_it_is_unsticking(loop: _Loop) -> None:
    _react(loop, Rung.REFLEX, reflex_attempt=1)

    request = loop.sent.pop()
    assert request.cancel_tasks == [repr(loop)]
    assert request.cancels_itself
    assert request.block_lower_priority


def test_reflex_releases_through_the_ledger_rather_than_blind(
    loop: _Loop, mocker: MockerFixture
) -> None:
    """
    A latched direction key is the commonest cause of a Stall, and
    `release_directions` reads the Held-Keys Ledger - so it sends nothing for a
    key that is not down and cannot emit a phantom release (**A6**).
    """
    release = mocker.patch(
        "maple.decision_makers.mixins._recovery_mixins.controller.release_directions"
    )
    jump = mocker.patch(
        "maple.decision_makers.mixins._recovery_mixins.random_jump",
        return_value=mocker.Mock(send=mocker.AsyncMock()),
    )
    mocker.patch(
        "maple.decision_makers.mixins._recovery_mixins.asyncio.sleep",
        mocker.AsyncMock(),
    )
    import asyncio

    asyncio.run(loop._wait_and_random_jump(1234, "space"))

    release.assert_called_once_with(1234)
    jump.assert_called_once_with(1234, "space")


# --- Abandon --------------------------------------------------------------------


def test_abandon_actually_changes_where_the_loop_is_heading(loop: _Loop) -> None:
    before = loop.data.next_target

    _react(loop, Rung.ABANDON, abandon_count=1)

    assert loop.data.next_target != before


def test_abandon_advances_the_feature_cycle_where_there_is_one(
    data: BotData, mocker: MockerFixture
) -> None:
    """
    Both target update functions return the *current* target until the character
    is within threshold of it, which is exactly what keeps a Stuck loop stuck:
    re-deciding cannot change where it is going.
    """
    mocker.patch(
        "maple.decision_makers.mixins._recovery_mixins.controller.key_binds",
        return_value={"jump": "space"},
    )
    data.set_static("current_minimap", _Minimap(cycle=True))
    loop = _Loop(data)
    loop._create_rotation_attributes()

    first = loop._abandon_current_target()
    second = loop._abandon_current_target()

    assert first != second


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

    assert "Rotation" in loop.disabled
    request = loop.sent.pop()
    assert request.discord_request is not None
    assert request.procedure is loop._release_movement_keys


def test_escalate_is_idempotent(loop: _Loop) -> None:
    """
    The disable takes effect when the disabler thread cancels the task, so one or
    more further cycles reach here first - each of which would otherwise ship
    another alert and another key-release Action.
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
    loop._react_to(Reaction(Symptom.STARVATION, None, (99, 99)))

    request = loop.sent.pop()
    assert request.discord_request is not None
    assert request.procedure is loop._noop
    assert loop.disabled == []
