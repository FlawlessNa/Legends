"""
`ReactionsMixin._react`: the bot keeps reacting for the whole session.

Issue #478: `_react` removed each pick from the class-level list, so after 11 light
(or 6 advanced) reactions the list was empty and `random.choice` raised IndexError.
These tests drive the real mixin with `send` captured. The 10 second `@cooldown`
is a rate limit, not part of what is checked, so the undecorated function is called
(`__wrapped__`).
"""

import itertools
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from botting.core import ActionRequest
from maple.actions import priorities, write_in_chat
from maple.decision_makers.mixins import ReactionsMixin


class _Reactor(ReactionsMixin):
    def __init__(self) -> None:
        self.data = SimpleNamespace(  # type: ignore[assignment]
            ign="tester", handle=1234, current_client_img=None
        )
        self.sent: list[ActionRequest] = []
        self.send = self.sent.append

    def __str__(self) -> str:
        return "Reactor"

    def react(self, reaction_type: str) -> None:
        type(self)._react.__wrapped__(self, reaction_type)  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _restore_class_lists() -> Iterator[None]:
    light = list(ReactionsMixin._light_reactions)
    advanced = list(ReactionsMixin._advanced_reactions)
    yield
    ReactionsMixin._light_reactions[:] = light
    ReactionsMixin._advanced_reactions[:] = advanced


@pytest.mark.parametrize("reaction_type", ["light", "advanced"])
def test_reacting_past_the_list_length_keeps_sending_one_chat_request_each(
    reaction_type: str,
) -> None:
    reactor = _Reactor()
    count = 3 * len(ReactionsMixin._light_reactions)

    for _ in range(count):
        reactor.react(reaction_type)

    assert len(reactor.sent) == count
    for request in reactor.sent:
        assert request.procedure is write_in_chat
        assert request.priority == priorities.ANTI_DETECTION
        assert request.args[0] == 1234
        assert isinstance(request.args[1], str)


@pytest.mark.parametrize("reaction_type", ["light", "advanced"])
def test_reacting_never_mutates_the_class_level_lists(reaction_type: str) -> None:
    light = list(ReactionsMixin._light_reactions)
    advanced = list(ReactionsMixin._advanced_reactions)
    first, second = _Reactor(), _Reactor()

    for _ in range(len(light) + 1):
        first.react(reaction_type)
        second.react(reaction_type)

    assert ReactionsMixin._light_reactions == light
    assert ReactionsMixin._advanced_reactions == advanced
    assert len(first.sent) == len(second.sent) == len(light) + 1


def test_no_line_repeats_until_every_line_has_been_used() -> None:
    reactor = _Reactor()
    n = len(ReactionsMixin._advanced_reactions)

    for _ in range(n):
        reactor.react("advanced")

    lines = [request.args[1] for request in reactor.sent]
    assert sorted(lines) == sorted(ReactionsMixin._advanced_reactions)


def test_a_refill_never_repeats_the_previous_line_immediately() -> None:
    reactor = _Reactor()

    for _ in range(50 * len(ReactionsMixin._advanced_reactions)):
        reactor.react("advanced")

    lines = [request.args[1] for request in reactor.sent]
    assert all(a != b for a, b in itertools.pairwise(lines))
