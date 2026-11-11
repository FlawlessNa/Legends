"""
`Addressing`: each kind and case of chat line maps to its `Address` (#461).

The names and messages are invented.
"""

from dataclasses import dataclass

import pytest

from maple.chat_replies import addressing
from maple.chat_replies.addressing import (
    NO_EVIDENCE,
    Address,
    Addressing,
    Evidence,
    judge_gate,
    strongest,
)
from maple.chat_replies.line import ReadLine
from maple.screen.chat import ChatKind

IGN = "Mapler"


@dataclass(frozen=True)
class Line:
    kind: ChatKind
    speaker: str | None
    message: str | None
    outgoing: bool = False


@pytest.mark.parametrize(
    ("line", "address"),
    [
        # Whispers to us, and every party or buddy line.
        (Line(ChatKind.WHISPER, "Bob", "hi u there?"), Address.MUST),
        (Line(ChatKind.PARTY, "Bob", "where r u"), Address.MUST),
        (Line(ChatKind.BUDDY, "Ann", "lol"), Address.MUST),
        # A general line naming us, as a whole word, in any case.
        (Line(ChatKind.GENERAL, "Bob", "mapler hi"), Address.MUST),
        (Line(ChatKind.GENERAL, "Bob", "hey MAPLER, party?"), Address.MUST),
        (Line(ChatKind.GENERAL, "Bob", "u there Mapler?"), Address.MUST),
        # Not as a whole word: another name.
        (Line(ChatKind.GENERAL, "Bob", "maplers r cool"), Address.JUDGE),
        (Line(ChatKind.GENERAL, "Bob", "xmapler hi"), Address.JUDGE),
        # Any other general line, also one the reader couldn't split.
        (Line(ChatKind.GENERAL, "Ann", "lol"), Address.JUDGE),
        (Line(ChatKind.GENERAL, None, None), Address.JUDGE),
        # Our own lines.
        (Line(ChatKind.WHISPER, "Bob", "ya", outgoing=True), Address.IGNORE),
        (Line(ChatKind.GENERAL, IGN, "brb"), Address.IGNORE),
        (Line(ChatKind.GENERAL, "MAPLER", "brb"), Address.IGNORE),
        # The kinds never answered, even naming us.
        (Line(ChatKind.MEGAPHONE, "Bob", "mapler hi"), Address.IGNORE),
        (Line(ChatKind.SYSTEM, None, "You have gained an item"), Address.IGNORE),
        (Line(ChatKind.UNKNOWN, None, None), Address.IGNORE),
        # A GM line.
        (Line(ChatKind.GM, "Gee", "hello"), Address.GM),
    ],
)
def test_each_kind_and_case_maps_to_its_address(line: Line, address: Address) -> None:
    assert Addressing(IGN).classify(line) is address


@pytest.mark.parametrize(
    "later",
    [
        Line(ChatKind.GENERAL, "Gee", "hello"),
        Line(ChatKind.WHISPER, "Gee", "are you there?"),
        Line(ChatKind.GENERAL, "gee", "hello"),
    ],
)
def test_a_later_line_from_a_speaker_seen_as_gm_is_gm(later: Line) -> None:
    classifier = Addressing(IGN)
    assert classifier.classify(later) is not Address.GM

    classifier.classify(Line(ChatKind.GM, "Gee", "hi"))

    assert classifier.classify(later) is Address.GM
    assert classifier.classify(Line(ChatKind.GENERAL, "Bob", "hi")) is Address.JUDGE


def test_our_whisper_to_a_gm_is_still_ours() -> None:
    # An outgoing whisper may read the GM's name as its speaker.
    classifier = Addressing(IGN)
    classifier.classify(Line(ChatKind.GM, "Gee", "hi"))

    reply = Line(ChatKind.WHISPER, "Gee", "hello, yes", outgoing=True)

    assert classifier.classify(reply) is Address.IGNORE


def test_gm_speakers_are_remembered_per_classifier() -> None:
    first, second = Addressing(IGN), Addressing(IGN)
    first.classify(Line(ChatKind.GM, "Gee", "hi"))

    assert second.classify(Line(ChatKind.GENERAL, "Gee", "hi")) is Address.JUDGE


def test_the_judge_gate_passes_every_line_for_now() -> None:
    assert judge_gate(Line(ChatKind.GENERAL, "Ann", "lol"), NO_EVIDENCE)


def test_a_line_the_judge_gate_rejects_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[ReadLine, Evidence]] = []

    def reject(line: ReadLine, evidence: Evidence) -> bool:
        seen.append((line, evidence))
        return False

    monkeypatch.setattr(addressing, "judge_gate", reject)
    line = Line(ChatKind.GENERAL, "Ann", "lol")
    evidence = Evidence()

    assert Addressing(IGN).classify(line, evidence) is Address.IGNORE
    assert seen == [(line, evidence)]
    # Only `JUDGE` lines go through the gate.
    assert Addressing(IGN).classify(Line(ChatKind.WHISPER, "Bob", "hi")) is Address.MUST
    assert len(seen) == 1


def test_strongest_is_gm_then_must_then_judge() -> None:
    assert strongest([Address.JUDGE, Address.GM, Address.MUST]) is Address.GM
    assert strongest([Address.JUDGE, Address.MUST]) is Address.MUST
    assert strongest([Address.JUDGE]) is Address.JUDGE
