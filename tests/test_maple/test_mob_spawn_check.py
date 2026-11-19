"""
`CheckMobsStillSpawn`'s takeover (#441): an ordinary DecisionMaker holding a
Pause on mob hitting and a Claim on `DESTINATION` for as long as its failsafe
runs, which leaves nothing paused or claimed behind, however it ends.

The Pauses, the Claim, the Supervisor that holds the Pauses and the Provider
that serves `DESTINATION` are the production ones; the chat toggle, the
reactions and the mob count are stubbed, and no loop runs: the failsafe is
driven directly. No game client.
"""

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from botting.core import BotData, DecisionMaker
from botting.core.supervisor import USER, PauseKind, Supervisor, resolve_pauses
from botting.screen import Reading
from maple.decision_makers import (
    CheckMobsStillSpawn,
    CheckStillInMap,
    MobsHitting,
    Rotation,
    TelecastMobsHitting,
)
from maple.decision_makers.providers import DESTINATION
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from maple.telemetry_events import RECOVERY_MOB_SPAWN_RESTORED
from tests.test_maple.movement_lab.fixture_maps import walk_corridor

from .serving import destination

WORLD = WorldMap.from_map_data(walk_corridor())


def _here() -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(50.0, 0.0, PositionSource.FUSED), 0.0)


class _Bot:
    """A Bot's mob-spawn check, mob hitting, and the Supervisor holding Pauses."""

    def __init__(self, mocker: MockerFixture) -> None:
        self.emitted: list[str] = []
        mocker.patch(
            "botting.core.decision_maker.emit_event",
            side_effect=lambda _cid, event_type, *args, **kwargs: self.emitted.append(
                event_type
            ),
        )
        provider = destination(WORLD, _here)
        self.data: BotData = provider.data
        self.check = CheckMobsStillSpawn(
            {},  # pyright: ignore[reportArgumentType] - nothing asks it for a proxy
            self.data,
            Mock(),
            mob_spawn_alert_timer=60.0,
            mob_spawn_alert_threshold=3,
        )
        self.hitting = object.__new__(MobsHitting)
        self.telecast = object.__new__(TelecastMobsHitting)
        self.supervisor = Supervisor(
            "T",
            [self.check, self.hitting, self.telecast],
            resolve_pauses([CheckMobsStillSpawn]),
        )
        self.toggles = 0

        async def validated(*args: object, **kwargs: object) -> None:
            self.toggles += 1

        self.check._validate_request_async = validated  # type: ignore[method-assign]
        self.check._toggle_chat_request = lambda: None  # type: ignore[method-assign,assignment,return-value]
        self.reactions = Mock()
        self.check._reactions = self.reactions

    def paused(self, cls: type[DecisionMaker]) -> list[PauseKind]:
        return [pause.kind for pause in self.supervisor.held(cls)]

    def procedure(self, run: Callable[[], Any]) -> None:
        """Stands in for the wander: what runs while the failsafe holds."""
        self.check._failsafe_procedure = run  # type: ignore[method-assign]


@pytest.fixture
def bot(mocker: MockerFixture) -> _Bot:
    return _Bot(mocker)


def test_the_failsafe_pauses_mob_hitting_and_wanders_until_mobs_return(
    bot: _Bot,
) -> None:
    during: dict[str, object] = {}

    async def mobs_return() -> None:
        during["hitting"] = bot.paused(MobsHitting)
        during["telecast"] = bot.paused(TelecastMobsHitting)
        during["claim"] = bot.data.claim_on(DESTINATION)
        await asyncio.sleep(0)

    bot.procedure(mobs_return)

    asyncio.run(bot.check._failsafe())

    assert during["hitting"] == [PauseKind.SCOPED]
    assert during["telecast"] == [PauseKind.SCOPED]
    claim = during["claim"]
    assert claim is not None
    assert claim.holder == f"CheckMobsStillSpawn({bot.data.ign})"  # type: ignore[attr-defined]
    # Handed back once mobs returned, and the chat shown again.
    assert bot.paused(MobsHitting) == []
    assert bot.paused(TelecastMobsHitting) == []
    assert bot.data.claim_on(DESTINATION) is None
    assert bot.toggles == 2
    assert RECOVERY_MOB_SPAWN_RESTORED in bot.emitted


def test_the_failsafe_cancelled_half_way_leaves_nothing_paused_or_claimed(
    bot: _Bot,
) -> None:
    """
    A Pause on the check itself (`CheckStillInMap` off the map, Discord PAUSE)
    or the Bot ending cancels its decision mid-failsafe: the legacy disable and
    hijack it replaced were left in place then.
    """
    wandering = asyncio.Event()

    async def wander_for_ever() -> None:
        wandering.set()
        await asyncio.Event().wait()

    bot.procedure(wander_for_ever)
    before = bot.data.read(DESTINATION)

    async def scenario() -> None:
        failsafe = asyncio.create_task(bot.check._failsafe())
        await wandering.wait()
        assert bot.paused(MobsHitting) == [PauseKind.SCOPED]
        assert bot.data.claim_on(DESTINATION) is not None
        failsafe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await failsafe

    asyncio.run(scenario())

    assert bot.paused(MobsHitting) == []
    assert bot.paused(TelecastMobsHitting) == []
    assert bot.data.claim_on(DESTINATION) is None
    assert bot.data.read(DESTINATION) == before, (
        "the Provider's own destination is back"
    )


def test_a_failsafe_that_times_out_stops_the_bot_for_the_user(bot: _Bot) -> None:
    """
    The classes the legacy shim left disabled, mob hitting included, now held
    by the user until Discord `RESUME`, and taken before the failsafe's own
    Pause on mob hitting is released, so mob hitting never runs in between.
    """

    async def times_out() -> None:
        raise TimeoutError

    bot.procedure(times_out)
    paused = Mock(wraps=bot.check.pause_for_user)
    bot.check.pause_for_user = paused  # type: ignore[method-assign]

    asyncio.run(bot.check._failsafe())

    paused.assert_called_once_with(
        Rotation,
        CheckMobsStillSpawn,
        CheckStillInMap,
        MobsHitting,
        TelecastMobsHitting,
        reason="mobs did not spawn again",
    )
    assert bot.paused(MobsHitting) == [PauseKind.USER]
    assert bot.paused(CheckMobsStillSpawn) == [PauseKind.USER]
    assert all(p.holder == USER for p in bot.supervisor.held(MobsHitting))
    assert bot.data.claim_on(DESTINATION) is None
    bot.reactions.react.assert_called_once_with("advanced")
    assert bot.toggles == 1, "the chat was hidden, and never shown again"


def test_what_it_pauses_and_steers_is_declared() -> None:
    assert resolve_pauses([CheckMobsStillSpawn])[CheckMobsStillSpawn] == {
        MobsHitting,
        TelecastMobsHitting,
        Rotation,
        CheckMobsStillSpawn,
        CheckStillInMap,
    }
    assert CheckMobsStillSpawn.steers == (DESTINATION,)
