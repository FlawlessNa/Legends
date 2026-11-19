"""
`AreaWatch` (#580): the alert when someone settles in the Hunting Area, the
Pause it holds on the mob-spawn failsafe meanwhile (D8), the stand-by when
nothing is left to go for, and the message when they leave.

The Pauses and the Supervisor that holds them are the production ones, and the
keys are served as a Bot serves them; the presence is scripted, one value per
decision, and the clock and the wait between two decisions are stood in for, so
a run of minutes takes no time. Nothing is sent to Main Process: the Actions
are read off the pipe. No game client.
"""

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.core import BotData, WindowProvider, action_name
from botting.core.supervisor import PauseKind, Supervisor, resolve_pauses
from botting.screen import Frame
from maple.decision_makers import (
    AreaWatch,
    CheckMobsStillSpawn,
    MobsHitting,
    Rotation,
    TelecastMobsHitting,
    area_watch,
)
from maple.decision_makers.area_watch import STAND_BY_AFTER
from maple.decision_makers.providers import (
    AREA_PRESENCE,
    FRAME,
    HANDLE,
    AreaPresence,
    ClientProvider,
    HuntingAreaProvider,
)
from maple.telemetry_events import (
    AREA_PLAYER_LEFT,
    AREA_PLAYER_SETTLED,
    AREA_STAND_BY,
)

NOBODY = AreaPresence(settled=False, others=(), free_share=1.0, inside=0)
SETTLED = AreaPresence(settled=True, others=((0.0, 0.0),), free_share=0.5, inside=1)
CROWDED = AreaPresence(settled=True, others=((0.0, 0.0),), free_share=0.0, inside=2)
PIXELS = np.full((4, 6, 3), 9, np.uint8)
HANDLE_VALUE = 4242


def _alerts(sent: list[Any]) -> list[Any]:
    return [r for r in sent if r.discord_request is not None]


class _Bot:
    """An `AreaWatch`, the DecisionMakers it pauses, and the Supervisor."""

    def __init__(
        self, mocker: MockerFixture, tmp_path: Path, *, discord: bool = True
    ) -> None:
        self.emitted: list[tuple[str, Any]] = []
        mocker.patch(
            "botting.core.decision_maker.emit_event",
            side_effect=lambda _cid, event_type, payload=None, **_: self.emitted.append(
                (event_type, payload)
            ),
        )
        config = tmp_path / "discord.ini"
        if discord:
            config.write_text("[discord]\n", encoding="utf-8")
        self.now = 1000.0
        #: What `AREA_PRESENCE` reads now.
        self.presence = NOBODY
        #: What `presence` becomes after each wait; the run is cancelled when
        #: it is used up while someone is still settled.
        self.script: list[AreaPresence] = []
        #: What the Pauses on the failsafe were, at each wait.
        self.failsafe_paused: list[bool] = []
        data = BotData("T")
        data.provide(
            AREA_PRESENCE,
            object.__new__(HuntingAreaProvider),
            lambda: self.presence,
            threshold=1e-9,  # read afresh each time
        )
        frame = Frame(PIXELS, (6, 4), 0.0, True, True)
        data.provide(FRAME, object.__new__(ClientProvider), lambda: frame)
        data.provide(HANDLE, object.__new__(WindowProvider), lambda: HANDLE_VALUE)
        self.data = data
        self.pipe = Mock()
        self.watch = AreaWatch(
            {},  # pyright: ignore[reportArgumentType] - nothing asks it for a proxy
            data,
            self.pipe,
            discord_config=config,
            clock=lambda: self.now,
            sleep=self._wait,
        )
        self.watch.setup()
        self.rotation = object.__new__(Rotation)
        self.check = object.__new__(CheckMobsStillSpawn)
        self.hitting = object.__new__(MobsHitting)
        self.telecast = object.__new__(TelecastMobsHitting)
        self.supervisor = Supervisor(
            "T",
            [self.watch, self.rotation, self.check, self.hitting, self.telecast],
            resolve_pauses([AreaWatch]),
        )

    async def _wait(self, seconds: float) -> None:
        self.failsafe_paused.append(bool(self.supervisor.held(CheckMobsStillSpawn)))
        self.now += seconds
        if not self.script:
            raise asyncio.CancelledError
        self.presence = self.script.pop(0)

    def decide(self, *presences: AreaPresence) -> None:
        """One decision, which reads `presences[0]` and then each next one after
        a wait; cancelled when they run out while someone is settled."""
        self.presence, *self.script = presences
        try:
            asyncio.run(self.watch._decide())  # pyright: ignore[reportPrivateUsage]
        except asyncio.CancelledError:
            pass

    @property
    def sent(self) -> list[Any]:
        return [call.args[0] for call in self.pipe.send.call_args_list]

    def events(self, event_type: str) -> list[Any]:
        return [payload for kind, payload in self.emitted if kind == event_type]

    def paused(self, cls: type) -> list[PauseKind]:
        return [pause.kind for pause in self.supervisor.held(cls)]


@pytest.fixture
def bot(mocker: MockerFixture, tmp_path: Path) -> _Bot:
    return _Bot(mocker, tmp_path)


def test_when_someone_settles_it_alerts_once_with_the_game_window(bot: _Bot) -> None:
    bot.decide(SETTLED, SETTLED, SETTLED, SETTLED)

    [alert] = _alerts(bot.sent)
    assert alert.discord_request.img is PIXELS or np.array_equal(
        alert.discord_request.img, PIXELS
    )
    assert "settled" in alert.discord_request.msg
    assert bot.events(AREA_PLAYER_SETTLED) == [{"inside": 1, "free_share": 0.5}]
    assert len(bot.sent) == 1, "the alert is the only Action: no key, no cancel"
    assert alert.cancel_tasks == []


def test_it_alerts_again_for_the_next_player_who_settles(bot: _Bot) -> None:
    bot.decide(SETTLED, NOBODY)
    bot.decide(SETTLED, NOBODY)

    assert len(bot.events(AREA_PLAYER_SETTLED)) == 2
    assert len(bot.events(AREA_PLAYER_LEFT)) == 2


def test_d8_the_failsafe_is_paused_from_settled_until_it_ends(bot: _Bot) -> None:
    assert bot.paused(CheckMobsStillSpawn) == []

    bot.decide(SETTLED, SETTLED, SETTLED, NOBODY)

    assert bot.failsafe_paused == [True, True, True]
    assert bot.paused(CheckMobsStillSpawn) == [], "released when settled ends"
    assert bot.paused(Rotation) == []


def test_d8_the_pause_is_released_when_area_watch_is_cancelled(bot: _Bot) -> None:
    bot.decide(SETTLED, SETTLED)  # cancelled while still settled

    assert bot.failsafe_paused == [True, True]
    assert bot.paused(CheckMobsStillSpawn) == []


def test_a_cancelled_area_watch_resumed_does_not_alert_twice(bot: _Bot) -> None:
    bot.decide(SETTLED, SETTLED)
    bot.decide(SETTLED, SETTLED)

    assert len(bot.events(AREA_PLAYER_SETTLED)) == 1
    assert len(_alerts(bot.sent)) == 1
    assert bot.failsafe_paused == [True, True, True, True]


def test_it_stands_by_once_nothing_is_left_for_the_stand_by_time(bot: _Bot) -> None:
    ticks = int(STAND_BY_AFTER)
    bot.decide(SETTLED, *[CROWDED] * (ticks + 5))

    standing = [r for r in bot.sent if r.cancel_tasks]
    [action] = standing
    assert action.cancel_tasks == [action_name(Rotation, "T")]
    assert action.procedure is area_watch._release_movement_keys  # pyright: ignore[reportPrivateUsage]
    assert action.args == (HANDLE_VALUE,)
    assert "standing by" in action.discord_request.msg
    assert np.array_equal(action.discord_request.img, PIXELS)
    assert bot.events(AREA_STAND_BY) == [{"inside": 2, "free_share": 0.0}]
    assert bot.paused(Rotation) == [PauseKind.USER]
    assert bot.paused(CheckMobsStillSpawn) == [PauseKind.USER]
    assert bot.paused(MobsHitting) == []
    assert bot.paused(TelecastMobsHitting) == []
    assert bot.paused(AreaWatch) == []


def test_it_does_not_stand_by_before_the_stand_by_time(bot: _Bot) -> None:
    bot.decide(SETTLED, *[CROWDED] * (int(STAND_BY_AFTER) - 5))

    assert bot.events(AREA_STAND_BY) == []
    assert bot.paused(Rotation) == []


def test_a_break_in_the_crowding_restarts_the_stand_by_time(bot: _Bot) -> None:
    half = int(STAND_BY_AFTER) - 20
    bot.decide(SETTLED, *[CROWDED] * half, SETTLED, *[CROWDED] * half)

    assert bot.events(AREA_STAND_BY) == []


def test_it_stands_by_again_only_after_free_share_rose_and_fell(bot: _Bot) -> None:
    ticks = int(STAND_BY_AFTER) + 5
    # `RESUME` is never asked about: the long crowding alone stands by once.
    bot.decide(SETTLED, *[CROWDED] * (2 * ticks))
    assert len(bot.events(AREA_STAND_BY)) == 1

    # Crowded again with no rise in between: no second stand-by. After a rise
    # to above 0, each long crowding stands by once more.
    bot.decide(CROWDED, *[CROWDED] * ticks)
    assert len(bot.events(AREA_STAND_BY)) == 1
    bot.decide(SETTLED, *[CROWDED] * ticks, SETTLED, *[CROWDED] * ticks)
    assert len(bot.events(AREA_STAND_BY)) == 3


def test_when_settled_ends_it_says_so(bot: _Bot) -> None:
    bot.decide(SETTLED, SETTLED, NOBODY)

    assert len(bot.events(AREA_PLAYER_LEFT)) == 1
    last = _alerts(bot.sent)[-1].discord_request.msg
    assert "left" in last
    assert "RESUME" not in last
    assert len(_alerts(bot.sent)) == 2


def test_after_standing_by_the_last_message_adds_resume(bot: _Bot) -> None:
    bot.decide(SETTLED, *[CROWDED] * (int(STAND_BY_AFTER) + 5), NOBODY)

    assert len(bot.events(AREA_PLAYER_LEFT)) == 1
    assert "; send `RESUME` if the bot is still standing by" in (
        _alerts(bot.sent)[-1].discord_request.msg
    )


def test_a_stand_by_from_an_earlier_player_is_not_told_for_the_next(
    bot: _Bot,
) -> None:
    bot.decide(SETTLED, *[CROWDED] * (int(STAND_BY_AFTER) + 5), NOBODY)
    bot.decide(SETTLED, NOBODY)

    assert "RESUME" not in _alerts(bot.sent)[-1].discord_request.msg


def test_with_no_discord_config_it_sends_no_request_and_does_the_rest(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    bot = _Bot(mocker, tmp_path, discord=False)

    bot.decide(SETTLED, *[CROWDED] * (int(STAND_BY_AFTER) + 5), NOBODY)

    assert _alerts(bot.sent) == []
    assert len(bot.events(AREA_PLAYER_SETTLED)) == 1
    assert len(bot.events(AREA_STAND_BY)) == 1
    assert len(bot.events(AREA_PLAYER_LEFT)) == 1
    assert [r.cancel_tasks for r in bot.sent] == [[action_name(Rotation, "T")]], (
        "the release of the keys still goes"
    )
    assert bot.paused(Rotation) == [PauseKind.USER]


def test_with_no_one_settled_it_does_nothing(bot: _Bot) -> None:
    bot.decide(NOBODY)

    assert bot.sent == []
    assert bot.emitted == []


def test_what_it_pauses_and_cancels_is_declared() -> None:
    assert AreaWatch.pauses == (Rotation, CheckMobsStillSpawn)
    assert AreaWatch.cancels == (Rotation,)
    assert resolve_pauses([AreaWatch])[AreaWatch] == {Rotation, CheckMobsStillSpawn}
    assert AreaWatch.reads == (AREA_PRESENCE, FRAME, HANDLE)


def test_the_stand_by_time_is_180_seconds() -> None:
    assert STAND_BY_AFTER == 180.0
