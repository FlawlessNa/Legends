"""
`Reactions.react`: the bot keeps reacting for the whole session, and every holder
shares one cooldown.

Issue #478: `_react` removed each pick from the class-level list, so after 11 light
(or 6 advanced) reactions the list was empty and `random.choice` raised IndexError.
These tests drive the real `Reactions` with `send` captured. The 10 second
`@cooldown` is a rate limit, not part of what is checked, so the undecorated
function is called (`__wrapped__`), except where the cooldown is what is checked.
"""

import itertools
import time
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from botting.core import HANDLE, ActionRequest, Key
from botting.utilities import functions_helpers
from maple.actions import DEFAULT_CHAT_KEYS, priorities, write_in_chat
from maple.decision_makers.providers import CHAT_KEYS, FRAME
from maple.decision_makers.reactions import Reactions

KEYS = {**DEFAULT_CHAT_KEYS, "general": "g"}
"""The character's chat keys, as its bot read them at startup."""


class _Reactor:
    """A holder of `Reactions`: it names, sends, and reads its keys."""

    def __init__(self) -> None:
        self.data = SimpleNamespace(ign="tester")
        self.values: dict[Key[Any], object] = {
            HANDLE: 1234,
            CHAT_KEYS: KEYS,
            FRAME: SimpleNamespace(pixels=None),
        }
        self.sent: list[ActionRequest] = []
        self.reactions = Reactions(self, self)  # pyright: ignore[reportArgumentType] - a stand-in

    def __str__(self) -> str:
        return "Reactor"

    def read(self, key: Key[Any]) -> object:
        return self.values[key]

    def send(self, request: ActionRequest) -> None:
        self.sent.append(request)

    def react(self, reaction_type: str) -> None:
        Reactions.react.__wrapped__(self.reactions, reaction_type)  # pyright: ignore[reportFunctionMemberAccess]


@pytest.fixture(autouse=True)
def _restore_class_lists() -> Iterator[None]:
    light = list(Reactions.LIGHT)
    advanced = list(Reactions.ADVANCED)
    yield
    Reactions.LIGHT[:] = light
    Reactions.ADVANCED[:] = advanced


@pytest.mark.parametrize("reaction_type", ["light", "advanced"])
def test_reacting_past_the_list_length_keeps_sending_one_chat_request_each(
    reaction_type: str,
) -> None:
    reactor = _Reactor()
    count = 3 * len(Reactions.LIGHT)

    for _ in range(count):
        reactor.react(reaction_type)

    assert len(reactor.sent) == count
    for request in reactor.sent:
        assert request.procedure is write_in_chat
        assert request.priority == priorities.ANTI_DETECTION
        assert request.args[0] == 1234
        assert isinstance(request.args[1], str)
        assert request.kwargs == {"keys": KEYS}


@pytest.mark.parametrize("reaction_type", ["light", "advanced"])
def test_reacting_never_mutates_the_class_level_lists(reaction_type: str) -> None:
    light = list(Reactions.LIGHT)
    advanced = list(Reactions.ADVANCED)
    first, second = _Reactor(), _Reactor()

    for _ in range(len(light) + 1):
        first.react(reaction_type)
        second.react(reaction_type)

    assert Reactions.LIGHT == light
    assert Reactions.ADVANCED == advanced
    assert len(first.sent) == len(second.sent) == len(light) + 1


def test_no_line_repeats_until_every_line_has_been_used() -> None:
    reactor = _Reactor()
    n = len(Reactions.ADVANCED)

    for _ in range(n):
        reactor.react("advanced")

    lines = [request.args[1] for request in reactor.sent]
    assert sorted(lines) == sorted(Reactions.ADVANCED)


def test_a_refill_never_repeats_the_previous_line_immediately() -> None:
    reactor = _Reactor()

    for _ in range(50 * len(Reactions.ADVANCED)):
        reactor.react("advanced")

    lines = [request.args[1] for request in reactor.sent]
    assert all(a != b for a, b in itertools.pairwise(lines))


def test_an_advanced_reaction_alerts_discord_in_its_holders_name() -> None:
    reactor = _Reactor()

    reactor.react("advanced")

    (request,) = reactor.sent
    assert request.identifier.startswith("Reactor - Writing to chat #")
    assert request.discord_request is not None
    assert request.discord_request.msg == "Reactor is failing"


# --- one cooldown for every holder ------------------------------------------------


def test_two_holders_share_the_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `CheckStillInMap` and `CheckMobsStillSpawn` used to react through the one
    `ReactionsMixin._react`, whose cooldown dropped a reaction within 10 s of the
    other's. Each holds a `Reactions` now; the drop stays.
    """
    # Past every reaction the session's earlier tests sent: the clock is shared.
    now = [time.perf_counter() + 1e6]
    monkeypatch.setattr(functions_helpers.time, "perf_counter", lambda: now[0])
    first = _Reactor()
    second = _Reactor()

    first.reactions.react("advanced")
    second.reactions.react("advanced")
    now[0] += 10.0
    second.reactions.react("advanced")

    assert len(first.sent) == 1
    assert len(second.sent) == 1
