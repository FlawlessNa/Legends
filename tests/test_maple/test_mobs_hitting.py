"""
`MobsHitting` on the attack list (#638, spec #631 § 4 "On screen" and § 6):
what it declares, which attack a decision casts and which way it faces, the
cast it sends, and the order a decision takes its turn in.

A decision runs against stand-ins for its keys, its gate and the detections:
no game client, no Manager, no Main Process. The attacks are the swordsman's,
armed on `test_reach`'s fixture (`swordOL`'s real boxes), so Power Strike and
Slash Blast reach (-73, -30) -> (-22, -16) facing left.
"""

import asyncio
import logging
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.controller.inputs.held_keys_ledger import InputState
from botting.core import (
    ActionRequest,
    BotData,
    Key,
    StartupRefused,
    action_name,
)
from botting.core.supervisor import resolve_cancels
from botting.models_abstractions import base_skill
from botting.utilities import Box
from maple.bots.training import TrainingBot
from maple.decision_makers import Rotation, mobs_hitting
from maple.decision_makers.mobs_hitting import PARTIAL_REACH_EVERY, MobsHitting
from maple.decision_makers.providers import (
    ATTACKS,
    CHAT_READER,
    FACING,
    FRAME,
    HANDLE,
    MOBS,
    ON_SCREEN_POSITION,
    Attack,
    Facing,
)
from maple.decision_makers.providers.on_screen import OnScreenPositionProvider
from maple.launchers.profile import ProfileError
from maple.model.characters.reach import armed
from maple.telemetry_events import COMBAT_MOBS_HIT, COMBAT_PARTIAL_REACH
from tests.test_maple.test_reach import (
    CATALOGUE,
    HEAL,
    POWER_STRIKE,
    SLASH_BLAST,
    SWORD,
)

IGN = "Tester"
#: 1:1: the play area is the client's own size.
CLIENT = (800, 600)
#: The character's feet at (400, 300).
CHARACTER_BOX = (390, 200, 410, 300)
#: Power Strike's and Slash Blast's reach on screen, facing left, at 1:1:
#: x 327 to 378, y 270 to 284.
REACH_LEFT, REACH_RIGHT, REACH_TOP, REACH_BOTTOM = 327, 378, 270, 284


def _armed(skill: Any, min_mobs: int) -> Attack:  # noqa: ANN401 - a fixture skill
    found = armed(skill, SWORD, CATALOGUE)
    return Attack(found.skill, found.reach, min_mobs, found.swings)


SLASH_BLAST_3 = _armed(SLASH_BLAST, 3)
POWER_STRIKE_1 = _armed(POWER_STRIKE, 1)
SWORDSMAN = (SLASH_BLAST_3, POWER_STRIKE_1)
#: Two-sided: Heal's box, symmetric about the feet.
HEAL_1 = Attack(HEAL, armed(HEAL, None, None).reach, 1)


def left_mob(x1: int, x2: int | None = None) -> tuple[int, int, int, int]:
    """A mob on the character's platform, from `x1` to `x2`: its box spans
    the reach's band."""
    return (x1, 250, x1 + 10 if x2 is None else x2, 300)


def mirrored(mob: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The mob, mirrored about the feet (x = 400)."""
    x1, y1, x2, y2 = mob
    return (800 - x2, y1, 800 - x1, y2)


# --- what it declares -----------------------------------------------------------


def test_it_has_no_mixin_in_its_class_hierarchy() -> None:
    assert not [c for c in MobsHitting.__mro__ if c.__name__.endswith("Mixin")]


def test_it_reads_the_attacks_and_the_on_screen_position_and_cancels_the_rotation() -> (
    None
):
    assert {ATTACKS, FACING, ON_SCREEN_POSITION} <= set(MobsHitting.reads)
    assert resolve_cancels([MobsHitting])[MobsHitting] == {Rotation}


def test_the_on_screen_position_is_its_providers() -> None:
    assert ON_SCREEN_POSITION.provider is OnScreenPositionProvider


# --- stand-ins ------------------------------------------------------------------


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


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class _Hitting:
    """A `MobsHitting` past `setup()`, and what it did."""

    def __init__(
        self,
        mocker: MockerFixture,
        *,
        attacks: tuple[Attack, ...] = SWORDSMAN,
        facing: Facing = Facing.CLOSEST,
        mobs: Sequence[tuple[int, int, int, int]] = (),
        on_ladder: bool = False,
        on_screen: Sequence[int] | None = CHARACTER_BOX,
        client: tuple[int, int] = CLIENT,
        chat_top: int | None = None,
    ) -> None:
        self.log: list[str] = []
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.clock = _Clock()
        self.pipe = _Pipe(self.log)
        self.mobs = list(mobs)
        hitting = MobsHitting({}, BotData(IGN), self.pipe, clock=self.clock)  # pyright: ignore[reportArgumentType] - stand-ins
        hitting.attacks = attacks
        hitting.gate = _Gate(self.log)  # pyright: ignore[reportAttributeAccessIssue] - a stand-in
        chat = mocker.Mock()
        chat.region.return_value = (
            None
            if chat_top is None
            else Box(left=0, right=800, top=chat_top, bottom=600)
        )
        width, height = client
        values: dict[Key[Any], object] = {
            HANDLE: 7,
            FRAME: SimpleNamespace(
                pixels=np.zeros((height, width, 3), np.uint8), client_size=client
            ),
            MOBS: (),
            CHAT_READER: chat,
            ON_SCREEN_POSITION: on_screen,
            FACING: facing,
            ATTACKS: attacks,
        }
        hitting.read = lambda key: values[key]
        hitting.peek = lambda key: None

        def emit(event: str, payload: Any, *args: object, **kwargs: object) -> None:  # noqa: ANN401 - any payload
            self.events.append((event, payload))

        hitting.emit = emit  # pyright: ignore[reportAttributeAccessIssue] - records

        def ladder() -> bool:
            self.log.append("ladder")
            return on_ladder

        def detect(*args: object, **kwargs: object) -> list[Sequence[int]]:
            self.log.append("detect")
            return list(self.mobs)

        hitting._currently_on_ladder = ladder  # pyright: ignore[reportPrivateUsage]
        mocker.patch.object(
            mobs_hitting, "get_mobs_positions_in_img", side_effect=detect
        )
        self.dm = hitting

    def decide(self) -> None:
        self.dm.correlation_id = "decision"
        asyncio.run(self.dm._decide())  # pyright: ignore[reportPrivateUsage]

    @property
    def cast(self) -> ActionRequest:
        [request] = self.pipe.sent
        return request

    def cast_skill(self) -> str:
        """The name of the skill the cast sends."""
        return self.cast.args[1].keywords["skill"].name

    def direction(self) -> str | None:
        return self.cast.args[1].keywords["direction"]

    def emitted(self, event: str) -> list[dict[str, Any]]:
        return [payload for kind, payload in self.events if kind == event]


# --- the turn -------------------------------------------------------------------


def test_a_decision_waits_for_the_gate_checks_the_ladder_detects_once_then_sends(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(340)])

    hitting.decide()

    assert hitting.log == ["enter", "ladder", "detect", "send"]


def test_the_cast_cancels_the_rotation_and_leaves_the_gate_from_main_process(
    mocker: MockerFixture,
) -> None:
    """Today's priority, blocking and cap, and the gate left by the callback."""
    hitting = _Hitting(mocker, mobs=[left_mob(340)])

    hitting.decide()

    request = hitting.cast
    assert request.identifier == f"MobsHitting({IGN})"
    assert request.cancel_tasks == [action_name(Rotation, IGN)]
    assert request.priority == 2
    assert request.block_lower_priority is True
    assert request.callbacks == [hitting.dm.gate.releaser]
    handle, _compiler, timeout = request.args
    assert handle == 7
    # The attack's own cast time: the weapon's, 699 ms for a sword at speed 4.
    assert timeout == 2 * 0.699 + 1.0
    assert "leave" not in hitting.log, "the callback leaves the gate"


@pytest.mark.parametrize(
    ("hitting_with", "expected"),
    [
        ({"on_ladder": True}, ["enter", "ladder", "leave"]),
        ({"mobs": []}, ["enter", "ladder", "detect", "leave"]),
        ({"mobs": [left_mob(340)], "on_screen": None}, ["enter", "ladder", "leave"]),
        (
            {"mobs": [left_mob(340)], "client": (3000, 2000)},
            ["enter", "ladder", "leave"],
        ),
    ],
    ids=["on a ladder", "no mob", "no character box", "no known play area"],
)
def test_a_decision_that_sends_nothing_leaves_the_gate_itself(
    mocker: MockerFixture, hitting_with: dict[str, Any], expected: list[str]
) -> None:
    hitting = _Hitting(mocker, **hitting_with)

    hitting.decide()

    assert hitting.log == expected
    assert not hitting.pipe.sent


def test_the_last_box_found_is_used_when_this_read_finds_none(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(340)], on_screen=None)
    hitting.dm.peek = lambda key: CHARACTER_BOX if key is ON_SCREEN_POSITION else None

    hitting.decide()

    assert hitting.log == ["enter", "ladder", "detect", "send"]


def test_on_start_frees_the_gate(mocker: MockerFixture) -> None:
    hitting = _Hitting(mocker)

    hitting.dm.on_start()

    assert hitting.log == ["reset"]


def test_a_client_with_no_known_play_area_is_logged_once_per_session(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(340)], client=(3000, 2000))

    with caplog.at_level(logging.WARNING):
        hitting.decide()
        hitting.decide()

    assert not hitting.pipe.sent
    assert len([r for r in caplog.records if "no known play area" in r.message]) == 1


# --- setup ----------------------------------------------------------------------


def test_a_profile_with_no_attacks_refuses_the_start_naming_attacks(
    mocker: MockerFixture,
) -> None:
    dm = MobsHitting({}, BotData(IGN), _Pipe([]))  # pyright: ignore[reportArgumentType] - stand-ins
    values: dict[Key[Any], object] = {CHAT_READER: mocker.Mock(), ATTACKS: None}
    dm.read = lambda key: values[key]

    with pytest.raises(StartupRefused, match=r"`attacks`"):
        dm.setup()


def test_training_skill_refuses_the_start_naming_attacks() -> None:
    with pytest.raises(
        ProfileError, match=r"`training_skill: Power Strike` is retired.*`attacks`"
    ):
        TrainingBot(
            "Someone",
            {},  # pyright: ignore[reportArgumentType] - metadata is never read here
            map="auto",
            character_class="Swordsman",
            training_skill="Power Strike",
        )


# --- the attack list ------------------------------------------------------------


@pytest.mark.parametrize(
    ("mobs", "cast"),
    [
        ([left_mob(330), left_mob(350)], "Power Strike"),
        ([left_mob(330), left_mob(345), left_mob(360)], "Slash Blast"),
    ],
    ids=["2 mobs", "3 mobs"],
)
def test_the_first_attack_with_its_min_mobs_in_reach_is_cast(
    mocker: MockerFixture, mobs: list[tuple[int, int, int, int]], cast: str
) -> None:
    hitting = _Hitting(mocker, mobs=mobs)

    hitting.decide()

    assert hitting.cast_skill() == cast
    assert hitting.direction() == "left"


def test_three_mobs_split_across_both_sides_dont_fire_a_one_sided_slash_blast(
    mocker: MockerFixture,
) -> None:
    """A one-sided reach is counted each way, never both ways added up."""
    mobs = [left_mob(330), left_mob(350), mirrored(left_mob(340))]
    hitting = _Hitting(mocker, mobs=mobs)

    hitting.decide()

    assert hitting.cast_skill() == "Power Strike"


def test_a_mob_box_overlapping_the_reach_by_one_pixel_counts(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(300, REACH_LEFT + 1)])

    hitting.decide()

    assert hitting.cast_skill() == "Power Strike"


@pytest.mark.parametrize(
    "mob",
    [
        left_mob(300, REACH_LEFT),
        left_mob(REACH_RIGHT, REACH_RIGHT + 10),
        (340, REACH_BOTTOM, 360, 320),
        (340, 200, 360, REACH_TOP),
    ],
    ids=["left", "right", "below", "above"],
)
def test_a_mob_box_a_pixel_clear_of_the_reach_doesnt_count(
    mocker: MockerFixture, mob: tuple[int, int, int, int]
) -> None:
    """It ends where the reach starts, or starts where it ends: no pixel shared."""
    hitting = _Hitting(mocker, mobs=[mob])

    hitting.decide()

    assert not hitting.pipe.sent


def test_the_reach_is_cut_at_the_chats_top(mocker: MockerFixture) -> None:
    mob = (340, REACH_BOTTOM - 4, 360, 320)
    reached = _Hitting(mocker, mobs=[mob])
    reached.decide()
    cut = _Hitting(mocker, mobs=[mob], chat_top=REACH_BOTTOM - 4)
    cut.decide()

    assert reached.cast_skill() == "Power Strike"
    assert not cut.pipe.sent


def test_the_reach_is_scaled_by_the_frame_over_the_play_area(
    mocker: MockerFixture,
) -> None:
    """
    2560 x 1440 draws a 1366 x 768 play area: a virtual px is 1.874 client px
    across, so the reach facing left goes from 1143 to 1239, feet at 1280.
    """
    character = (1270, 700, 1290, 800)
    near_far_edge = (1150, 700, 1160, 800)
    scaled = _Hitting(
        mocker, mobs=[near_far_edge], client=(2560, 1440), on_screen=character
    )
    scaled.decide()
    clear = _Hitting(
        mocker, mobs=[(1130, 700, 1143, 800)], client=(2560, 1440), on_screen=character
    )
    clear.decide()

    assert scaled.cast_skill() == "Power Strike"
    assert not clear.pipe.sent


# --- facing ---------------------------------------------------------------------


def test_a_two_sided_attack_sends_no_facing_prelude(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(base_skill, "skill_keys", lambda ign: {"Heal": "h"})
    hitting = _Hitting(mocker, attacks=(HEAL_1,), mobs=[left_mob(340)])

    hitting.decide()

    assert hitting.direction() is None
    keys = hitting.cast.args[1](InputState()).keys
    assert "h" in keys
    assert not {"left", "right"} & {k for k in keys if isinstance(k, str)}


def test_a_one_sided_attack_sends_its_facing_then_its_key(
    mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(base_skill, "skill_keys", lambda ign: {"Power Strike": "a"})
    hitting = _Hitting(mocker, mobs=[mirrored(left_mob(340))])

    hitting.decide()

    keys = [k for k in hitting.cast.args[1](InputState()).keys if isinstance(k, str)]
    assert keys.index("right") < keys.index("a")


@pytest.mark.parametrize(
    ("facing", "expected"),
    [(Facing.CLOSEST, "right"), (Facing.MOST, "left")],
)
def test_facing_picks_the_side_of_the_closest_mob_or_of_the_most_mobs(
    mocker: MockerFixture, facing: Facing, expected: str
) -> None:
    # Two mobs far left, one near right: all in Power Strike's reach.
    mobs = [left_mob(330), left_mob(340), mirrored(left_mob(365))]
    hitting = _Hitting(mocker, mobs=mobs, facing=facing)

    hitting.decide()

    assert hitting.cast_skill() == "Power Strike"
    assert hitting.direction() == expected


# --- telemetry ------------------------------------------------------------------


def test_mobs_hit_names_the_attack_and_each_counted_mobs_box_from_the_feet(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(330), left_mob(350), (0, 0, 10, 10)])

    hitting.decide()

    [hit] = hitting.emitted(COMBAT_MOBS_HIT)
    assert hit == {
        "mob_count": 2,
        "direction": "left",
        "attack": "Power Strike",
        "mobs": [
            {"left": -70, "top": -50, "right": -60, "bottom": 0},
            {"left": -50, "top": -50, "right": -40, "bottom": 0},
        ],
    }


def test_partial_reach_fires_for_a_mob_in_a_swing_and_out_of_the_reach(
    mocker: MockerFixture,
) -> None:
    """
    `swingO3` reaches 102 px in front, the overlap of the swings only 73: a mob
    from 300 to 320 is in the first and out of the second.
    """
    hitting = _Hitting(mocker, mobs=[left_mob(300, 320)])

    hitting.decide()

    assert not hitting.pipe.sent
    assert hitting.emitted(COMBAT_PARTIAL_REACH) == [
        {
            "attack": "Slash Blast",
            "mobs": [{"left": -100, "top": -50, "right": -80, "bottom": 0}],
        }
    ]


def test_partial_reach_doesnt_fire_for_a_mob_out_of_every_swing(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(100, 200)])

    hitting.decide()

    assert not hitting.events


def test_partial_reach_doesnt_fire_for_a_skill_based_reach(
    mocker: MockerFixture,
) -> None:
    hitting = _Hitting(mocker, attacks=(HEAL_1,), mobs=[left_mob(100, 140)])

    hitting.decide()

    assert not hitting.events


def test_partial_reach_fires_at_most_once_a_second(mocker: MockerFixture) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(300, 320)])

    hitting.decide()
    hitting.clock.now += PARTIAL_REACH_EVERY / 2
    hitting.decide()
    hitting.clock.now += PARTIAL_REACH_EVERY / 2
    hitting.decide()

    assert len(hitting.emitted(COMBAT_PARTIAL_REACH)) == 2


def test_a_decision_that_casts_reports_no_partial_reach(mocker: MockerFixture) -> None:
    hitting = _Hitting(mocker, mobs=[left_mob(340), left_mob(300, 320)])

    hitting.decide()

    assert hitting.cast_skill() == "Power Strike"
    assert not hitting.emitted(COMBAT_PARTIAL_REACH)
