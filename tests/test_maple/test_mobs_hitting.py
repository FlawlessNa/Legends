"""
`MobsHitting` and `TelecastMobsHitting` on the framework (#439): what they
declare, the cast they send, and the order a decision takes its turn in; and
the telecast's read of the rotation's plan (#442).

A decision runs against stand-ins for its keys and its gate: no game client,
no Manager, no Main Process.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core import ActionRequest, BotData, DecisionMaker, Key, action_name
from botting.core.supervisor import resolve_cancels
from maple.decision_makers import Rotation, TelecastMobsHitting, mobs_hitting
from maple.decision_makers.mobs_hitting import MobsHitting
from maple.decision_makers.providers import (
    CHAT_READER,
    FRAME,
    HANDLE,
    MOBS,
    MOVEMENTS,
    ON_SCREEN_POSITION,
)
from maple.decision_makers.providers.on_screen import OnScreenPositionProvider
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
)

IGN = "Tester"
CHARACTER_BOX = (90, 40, 110, 70)


# --- what they declare ----------------------------------------------------------


@pytest.mark.parametrize("cls", [MobsHitting, TelecastMobsHitting])
def test_it_has_no_mixin_in_its_class_hierarchy(cls: type[DecisionMaker]) -> None:
    assert not [c for c in cls.__mro__ if c.__name__.endswith("Mixin")]


@pytest.mark.parametrize("cls", [MobsHitting, TelecastMobsHitting])
def test_it_reads_the_on_screen_position_and_cancels_the_rotation(
    cls: type[DecisionMaker],
) -> None:
    assert ON_SCREEN_POSITION in cls.reads
    assert resolve_cancels([cls])[cls] == {Rotation}


def test_the_on_screen_position_keeps_its_legacy_name() -> None:
    """The unported smart rotation reads it by that name."""
    assert ON_SCREEN_POSITION.legacy_name == "current_on_screen_position"
    assert ON_SCREEN_POSITION.provider is OnScreenPositionProvider


# --- the cast -------------------------------------------------------------------


class _Gate:
    """Records the turns a decision takes, in `log`, as the real gate is used."""

    def __init__(self, log: list[str]) -> None:
        self.log = log

    async def enter(self) -> None:
        self.log.append("enter")

    async def leave(self) -> None:
        self.log.append("leave")

    def releaser(self) -> None:
        self.log.append("released")

    def reset(self) -> None:
        self.log.append("reset")


class _Pipe:
    def __init__(self, log: list[str]) -> None:
        self.log = log
        self.sent: list[ActionRequest] = []

    def send(self, request: ActionRequest) -> None:
        self.log.append("send")
        self.sent.append(request)


def _skill() -> SimpleNamespace:
    return SimpleNamespace(
        name="Genesis",
        animation_time=1.5,
        unidirectional=False,
        horizontal_screen_range=400,
        vertical_screen_range=200,
        vertical_up_screen_range=None,
        vertical_down_screen_range=None,
    )


def _hitting(
    mocker: MockerFixture,
    log: list[str],
    *,
    on_ladder: bool = False,
    mobs: int = 3,
    on_screen: tuple[int, int, int, int] | None = CHARACTER_BOX,
) -> MobsHitting:
    """A `MobsHitting` past `setup()`, whose keys, gate and detection stand in."""
    hitting = object.__new__(MobsHitting)
    DecisionMaker.__init__(hitting, {}, BotData(IGN), _Pipe(log))  # pyright: ignore[reportArgumentType] - stand-ins
    hitting.mob_threshold = 3
    hitting.training_skill = _skill()  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    hitting.gate = _Gate(log)  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
    chat = mocker.Mock()
    chat.region.return_value = None
    values: dict[Key[Any], object] = {
        HANDLE: 7,
        FRAME: SimpleNamespace(pixels=np.zeros((600, 800, 3), np.uint8)),
        MOBS: (),
        CHAT_READER: chat,
        ON_SCREEN_POSITION: on_screen,
    }
    hitting.read = lambda key: values[key]
    hitting.peek = lambda key: None

    def ladder() -> bool:
        log.append("ladder")
        return on_ladder

    def count(*args: object, **kwargs: object) -> int:
        log.append("count")
        return mobs

    hitting._currently_on_ladder = ladder
    mocker.patch.object(mobs_hitting, "mob_count_in_img", side_effect=count)
    return hitting


def _decide(hitting: MobsHitting) -> None:
    hitting.correlation_id = "decision"
    asyncio.run(hitting._decide())  # pyright: ignore[reportPrivateUsage]


def test_a_decision_waits_for_the_gate_checks_the_ladder_counts_then_sends(
    mocker: MockerFixture,
) -> None:
    log: list[str] = []
    hitting = _hitting(mocker, log)

    _decide(hitting)

    assert log == ["enter", "ladder", "count", "send"]


def test_the_cast_cancels_the_rotation_and_leaves_the_gate_from_main_process(
    mocker: MockerFixture,
) -> None:
    """Today's priority, blocking and cap, and the gate left by the callback."""
    log: list[str] = []
    hitting = _hitting(mocker, log)

    _decide(hitting)

    [request] = hitting.pipe.sent  # pyright: ignore[reportAttributeAccessIssue] - the stand-in's
    assert request.identifier == f"MobsHitting({IGN})"
    assert request.cancel_tasks == [action_name(Rotation, IGN)]
    assert request.cancel_tasks == [f"Rotation({IGN})"]
    assert request.priority == 2
    assert request.block_lower_priority is True
    assert request.callbacks == [hitting.gate.releaser]
    handle, _compiler, timeout = request.args
    assert handle == 7
    assert timeout == 2 * 1.5 + 1.0
    assert "leave" not in log, "the callback leaves the gate, once the cast is done"


@pytest.mark.parametrize(
    ("hitting_with", "expected"),
    [
        ({"on_ladder": True}, ["enter", "ladder", "leave"]),
        ({"mobs": 2}, ["enter", "ladder", "count", "leave"]),
        ({"on_screen": None}, ["enter", "ladder", "leave"]),
    ],
)
def test_a_decision_that_sends_nothing_leaves_the_gate_itself(
    mocker: MockerFixture, hitting_with: dict[str, Any], expected: list[str]
) -> None:
    log: list[str] = []
    hitting = _hitting(mocker, log, **hitting_with)

    _decide(hitting)

    assert log == expected


def test_the_last_box_found_is_used_when_this_read_finds_none(
    mocker: MockerFixture,
) -> None:
    """As `get_last_known_value` served it: the read, or the last box found."""
    log: list[str] = []
    hitting = _hitting(mocker, log, on_screen=None)
    hitting.peek = lambda key: CHARACTER_BOX if key is ON_SCREEN_POSITION else None

    _decide(hitting)

    assert log == ["enter", "ladder", "count", "send"]


def test_on_start_frees_the_gate(mocker: MockerFixture) -> None:
    log: list[str] = []
    hitting = _hitting(mocker, log)

    hitting.on_start()

    assert log == ["reset"]


# --- the telecast reads the rotation's plan (#442) -----------------------------


def _telecast(
    mocker: MockerFixture, log: list[str], plan: tuple[object, ...]
) -> tuple[TelecastMobsHitting, list[tuple[str | None, bool]]]:
    """A `TelecastMobsHitting` past `setup()`, whose plan is `plan`, and the
    compiles it asked `PathingProvider` for."""
    hitting = _hitting(mocker, log)
    telecast: Any = object.__new__(TelecastMobsHitting)
    telecast.__dict__.update(hitting.__dict__)
    reads = hitting.read
    telecast.read = lambda key: plan if key is MOVEMENTS else reads(key)
    telecast._teleport_skill = SimpleNamespace(name="Teleport")
    compiles: list[tuple[str | None, bool]] = []
    telecast._pathing = SimpleNamespace(
        compiler=lambda correlation_id, *, lead=True: compiles.append(
            (correlation_id, lead)
        )
    )
    telecast.emit = lambda *args, **kwargs: None
    return telecast, compiles


def test_the_telecast_reads_the_rotations_plan() -> None:
    assert MOVEMENTS in TelecastMobsHitting.reads
    assert set(MobsHitting.reads) <= set(TelecastMobsHitting.reads)


def test_a_plan_that_teleports_is_compiled_by_the_pathing_with_no_lead(
    mocker: MockerFixture,
) -> None:
    """The Path is the rotation's: no frame of the telecast's own to lead from."""
    log: list[str] = []
    teleport = _MovementComponent(MovementTypes.TELEPORT_RIGHT, 1)
    telecast, compiles = _telecast(mocker, log, (teleport,))

    _decide(telecast)

    assert compiles == [("decision", False)]
    assert log == ["enter", "ladder", "count", "send"]


def test_a_plan_with_no_teleport_casts_as_mob_hitting_does(
    mocker: MockerFixture,
) -> None:
    log: list[str] = []
    walk = _MovementComponent(MovementTypes.WALK_RIGHT, 80)
    telecast, compiles = _telecast(mocker, log, (walk,))

    _decide(telecast)

    assert compiles == []
    assert log == ["enter", "ladder", "count", "send"]
