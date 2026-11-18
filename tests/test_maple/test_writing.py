"""
`maple.actions.writing`: typing in the chat, and the keys that open each channel.

What reaches the client is recorded at `SendInput` and `PostMessage`
(`tests/sent_input.py`); `release_all`, `press`, `write` and the Held-Keys Ledger
run as they do live.
"""

import ast
import itertools
import pickle
import random
from collections.abc import Coroutine, Iterator
from configparser import ConfigParser, SectionProxy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from botting.controller import TypingPace
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger
from botting.core import ActionRequest
from botting.utilities import config_reader
from maple.actions import writing
from maple.actions.writing import (
    AFTER_OPENING,
    BEFORE_OPENING,
    BEFORE_SENDING,
    DEFAULT_CHAT_KEYS,
    read_chat_keys,
    reply_in_chat,
    write_in_chat,
)
from maple.bots.training import TrainingBot
from maple.decision_makers.mixins._reactions_mixins import ReactionsMixin
from maple.parsers import maple_parser
from maple.parsers.maple_parser import MapleParser
from maple.screen.sprites import StartupRefused
from tests import sent_input
from tests.sent_input import Event, SentInput

HANDLE = 1234
SEED = 460
IGN = "Testee"
MESSAGE = "hey, map's full"
RECIPIENT = "Bobby"
EXAMPLE = Path(__file__).resolve().parents[2] / "configs" / "keybindings.example.ini"

Keys = list[tuple[str, Event]]


@pytest.fixture(autouse=True)
def reset_ledger() -> Iterator[None]:
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> SentInput:
    return sent_input.install(monkeypatch, HANDLE)


def _press(key: str) -> Keys:
    return [(key, "keydown"), (key, "keyup")]


def _typed(text: str) -> Keys:
    return [step for char in text for step in _press(char)]


def _pace() -> TypingPace:
    return TypingPace(rng=random.Random(SEED))


def _reply(
    channel: str,
    whisper_to: str | None = None,
    keys: dict[str, str] | None = None,
) -> Coroutine[Any, Any, None]:
    return reply_in_chat(
        HANDLE,
        MESSAGE,
        channel,
        whisper_to,
        _pace(),
        keys=dict(DEFAULT_CHAT_KEYS) if keys is None else keys,
    )


def _send() -> Keys:
    """Enter sends the message; Enter again closes the chat input."""
    return _press("enter") + _press("enter")


# --- the key sequence ------------------------------------------------------------


@pytest.mark.parametrize(
    ("channel", "key"),
    [(c, k) for c, k in DEFAULT_CHAT_KEYS.items() if c != "whisper"],
)
def test_a_reply_opens_its_channel_types_the_message_and_sends_it(
    sent: SentInput, channel: str, key: str
) -> None:
    sent.run(_reply(channel))

    assert sent.keys() == _press(key) + _typed(MESSAGE) + _send()


def test_a_whisper_opens_the_whisper_types_the_recipient_then_the_message(
    sent: SentInput,
) -> None:
    sent.run(_reply("whisper", RECIPIENT))

    assert sent.keys() == (
        _press("h") + _typed(RECIPIENT) + _press("enter") + _typed(MESSAGE) + _send()
    )


def test_the_channel_key_is_pressed_and_the_text_typed_as_characters(
    sent: SentInput,
) -> None:
    sent.run(_reply("whisper", RECIPIENT))

    pressed = [step.key for step in sent.steps if not step.typed]
    typed = "".join(s.key for s in sent.steps if s.typed and s.event == "keydown")
    assert set(pressed) == {"h", "enter"}
    assert typed == RECIPIENT + MESSAGE


def test_a_reply_first_releases_every_held_key_and_leaves_none_held(
    sent: SentInput,
) -> None:
    HeldKeysLedger.record_step(HANDLE, ["right", "space"], ["keydown", "keydown"])

    sent.run(_reply("general"))

    released = sent.keys()[:2]
    assert sorted(released) == [("right", "keyup"), ("space", "keyup")]
    assert sent.keys()[2:] == _press("1") + _typed(MESSAGE) + _send()
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset()


def test_the_characters_chat_keys_open_the_channels(sent: SentInput) -> None:
    keys = read_chat_keys("{'party': 'p', 'whisper': 'w'}", IGN)

    sent.run(_reply("party", keys=keys))
    party = sent.keys()
    sent.steps.clear()
    sent.run(_reply("whisper", RECIPIENT, keys=keys))

    assert party[:2] == _press("p")
    assert sent.keys()[:2] == _press("w")


# --- the timing ------------------------------------------------------------------


def _index(sent: SentInput, key: str, event: Event, after: int = 0) -> int:
    return next(
        i
        for i, step in enumerate(sent.steps)
        if i >= after and (step.key, step.event) == (key, event)
    )


def test_the_character_stops_then_pauses_before_opening_the_channel(
    sent: SentInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    for seed in range(20):
        monkeypatch.setattr(writing, "random", random.Random(seed))
        HeldKeysLedger.record_step(HANDLE, "right", "keydown")
        sent.steps.clear()

        sent.run(_reply("general"))

        low, high = BEFORE_OPENING
        assert sent.keys()[0] == ("right", "keyup")
        assert low <= sent.gap_before(1) <= high


def test_typing_starts_once_the_chat_input_has_had_time_to_open(
    sent: SentInput,
) -> None:
    sent.run(_reply("general"))

    first_char = _index(sent, MESSAGE[0], "keydown")
    assert sent.gap_before(first_char) >= AFTER_OPENING[0]


def test_the_message_is_typed_at_the_pace(sent: SentInput) -> None:
    sent.run(_reply("general"))

    downs = [s for s in sent.steps if s.typed and s.event == "keydown"]
    gaps = [later.at - earlier.at for earlier, later in itertools.pairwise(downs)]
    assert gaps == pytest.approx(_pace().delays(MESSAGE)[:-1])


def test_the_reply_is_sent_a_short_pause_after_its_last_character(
    sent: SentInput, monkeypatch: pytest.MonkeyPatch
) -> None:
    for seed in range(20):
        monkeypatch.setattr(writing, "random", random.Random(seed))
        sent.steps.clear()

        sent.run(_reply("general"))

        enter = _index(sent, "enter", "keydown")
        assert sent.keys()[enter - 1] == (MESSAGE[-1], "keyup")
        low, high = BEFORE_SENDING
        assert low <= sent.gap_before(enter) <= high


# --- what is refused, before anything is sent ------------------------------------


@pytest.mark.parametrize(
    ("channel", "whisper_to", "refusal"),
    [
        ("whisper", None, "needs a recipient"),
        ("whisper", "", "needs a recipient"),
        ("general", RECIPIENT, "Only a whisper"),
        ("shout", None, "not recognized"),
    ],
)
def test_a_reply_that_cannot_be_typed_is_refused_with_nothing_sent(
    sent: SentInput, channel: str, whisper_to: str | None, refusal: str
) -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    with pytest.raises(ValueError, match=refusal):
        sent.run(_reply(channel, whisper_to))

    assert sent.steps == []
    assert HeldKeysLedger.keys_held(HANDLE) == frozenset({"right"})


# --- write_in_chat ---------------------------------------------------------------


def test_write_in_chat_takes_the_same_steps_at_the_controllers_delay(
    sent: SentInput,
) -> None:
    sent.run(write_in_chat(HANDLE, MESSAGE))

    assert sent.keys() == _press("1") + _typed(MESSAGE) + _send()
    downs = [s for s in sent.steps if s.typed and s.event == "keydown"]
    gaps = {round(b.at - a.at, 3) for a, b in itertools.pairwise(downs)}
    assert max(gaps) < 0.1


def test_write_in_chat_whispers_with_or_without_a_recipient(sent: SentInput) -> None:
    sent.run(write_in_chat(HANDLE, MESSAGE, "whisper", RECIPIENT))
    with_recipient = sent.keys()
    sent.steps.clear()
    sent.run(write_in_chat(HANDLE, MESSAGE, "whisper"))

    assert with_recipient == (
        _press("h") + _typed(RECIPIENT) + _press("enter") + _typed(MESSAGE) + _send()
    )
    assert sent.keys() == _press("h") + _press("enter") + _typed(MESSAGE) + _send()


def test_write_in_chat_opens_the_channel_with_the_keys_it_is_given(
    sent: SentInput,
) -> None:
    sent.run(write_in_chat(HANDLE, MESSAGE, "buddy", keys={"buddy": "b"}))

    assert sent.keys()[:2] == _press("b")


def test_a_silenced_write_in_chat_posts_its_keys_to_the_window(
    sent: SentInput,
) -> None:
    sent.run(write_in_chat(HANDLE, MESSAGE, silenced=True))

    assert sent.keys() == (_press("1") + [(char, "char") for char in MESSAGE] + _send())


def test_write_in_chat_refuses_an_unknown_channel(sent: SentInput) -> None:
    with pytest.raises(ValueError, match="shout"):
        sent.run(write_in_chat(HANDLE, MESSAGE, "shout"))

    assert sent.steps == []


# --- Chat Keys -------------------------------------------------------------------


def test_chat_keys_that_are_not_a_dict_are_refused() -> None:
    with pytest.raises(TypeError, match="must be a dict"):
        read_chat_keys("['general', '1']", IGN)


def test_a_section_without_chat_keys_keeps_every_channels_key() -> None:
    assert read_chat_keys(None, IGN) == {
        "general": "1",
        "party": "2",
        "buddy": "3",
        "guild": "4",
        "alliance": "5",
        "spouse": "6",
        "whisper": "h",
    }


def test_a_channel_chat_keys_leaves_out_keeps_its_key() -> None:
    keys = read_chat_keys("{'general': 'g'}", IGN)

    assert keys == {**DEFAULT_CHAT_KEYS, "general": "g"}


@pytest.mark.parametrize(
    ("raw", "names"),
    [
        ("{'shout': 'x'}", "shout"),
        ("{'general': 1}", "not a key"),
        ("{'general': 'f13'}", "not a key"),
        ("{'general': '1'", "not a dict literal"),
    ],
)
def test_chat_keys_that_are_not_channels_to_keys_are_refused(
    raw: str, names: str
) -> None:
    with pytest.raises(ValueError, match=names):
        read_chat_keys(raw, IGN)


def _example_section() -> SectionProxy:
    parser = config_reader("", full_path=str(EXAMPLE))
    assert isinstance(parser, ConfigParser)
    return parser["YourCharacterName"]


def test_the_example_keybindings_bind_every_channel_to_its_default_key() -> None:
    raw = _example_section().get("Chat Keys")

    assert raw is not None
    assert read_chat_keys(raw, IGN) == DEFAULT_CHAT_KEYS


def test_the_examples_other_bindings_still_read_alongside_chat_keys() -> None:
    """`key_binds` merges every dict of the section, `Chat Keys` included."""
    merged: dict[str, object] = {}
    for value in _example_section().values():
        merged.update(ast.literal_eval(value))

    assert merged["jump"] == "alt_right"
    assert merged["whisper"] == "h"


def test_chat_keys_reads_the_characters_section(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ini = tmp_path / "keybindings.ini"
    ini.write_text(f"[{IGN}]\nChat Keys = {{\n    'party': 'p',\n    }}\n")
    monkeypatch.setattr(
        writing,
        "config_reader",
        lambda name, section: config_reader(name, section, full_path=str(ini)),
    )

    keys = writing.chat_keys(IGN)

    assert keys == {**DEFAULT_CHAT_KEYS, "party": "p"}
    assert pickle.loads(pickle.dumps(keys)) == keys


# --- the callers -----------------------------------------------------------------


class _Reacting(ReactionsMixin):
    """The mixin on a bot that only records what it sends."""

    def __init__(self, chat_keys: dict[str, str]) -> None:
        self.data = SimpleNamespace(ign=IGN, handle=HANDLE, chat_keys=chat_keys)  # pyright: ignore[reportAttributeAccessIssue]
        self.sent: list[ActionRequest] = []
        self.send = self.sent.append


def test_a_reaction_writes_with_the_characters_chat_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The keys its bot read at startup, never read again here."""
    bound = {**DEFAULT_CHAT_KEYS, "general": "g"}
    monkeypatch.setattr(writing, "config_reader", _no_config)
    monkeypatch.setattr(ReactionsMixin, "_light_reactions", ["wtf"])
    reacting = _Reacting(bound)

    # Past `cooldown`, whose clock is shared by every bot in the process.
    ReactionsMixin._react.__wrapped__(reacting, "light")  # pyright: ignore[reportFunctionMemberAccess]

    (request,) = reacting.sent
    assert request.procedure is write_in_chat
    assert request.args == (HANDLE, "wtf")
    assert request.kwargs == {"keys": bound}


def test_writing_from_discord_uses_the_characters_chat_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound = {**DEFAULT_CHAT_KEYS, "general": "g"}
    monkeypatch.setattr(maple_parser, "find_client", lambda: HANDLE)
    monkeypatch.setattr(maple_parser, "chat_keys", {IGN: bound}.__getitem__)
    parser = object.__new__(MapleParser)

    request = parser.write("hello", IGN)

    assert request.procedure is write_in_chat
    assert request.kwargs == {"keys": bound}


def test_writing_from_discord_for_an_ign_with_no_bindings_uses_the_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(maple_parser, "find_client", lambda: HANDLE)
    monkeypatch.setattr(maple_parser, "chat_keys", {}.__getitem__)
    parser = object.__new__(MapleParser)

    request = parser.write("hello", "Nobody")

    assert request.kwargs == {"keys": DEFAULT_CHAT_KEYS}
    pickle.dumps(request.kwargs)


def _no_config(*args: object, **kwargs: object) -> None:
    raise AssertionError("the keybindings were read again after startup")


# --- read once, at startup (#477's review) ---------------------------------------


@pytest.fixture
def keybindings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """`configs/keybindings.ini` for the test to write, and no keys started yet."""
    ini = tmp_path / "keybindings.ini"
    monkeypatch.setattr(
        writing,
        "config_reader",
        lambda name, section: config_reader(name, section, full_path=str(ini)),
    )
    monkeypatch.setattr(writing, "_STARTED", {})
    return ini


def test_startup_reads_the_keys_once_and_the_parser_uses_them(
    monkeypatch: pytest.MonkeyPatch, keybindings: Path
) -> None:
    keybindings.write_text(f"[{IGN}]\nChat Keys = {{'party': 'p'}}\n")
    assert writing.startup_chat_keys(IGN) == {**DEFAULT_CHAT_KEYS, "party": "p"}

    # Edited mid-session: what started is what is used.
    keybindings.write_text(f"[{IGN}]\nChat Keys = {{'party': 'z'}}\n")
    monkeypatch.setattr(maple_parser, "find_client", lambda: HANDLE)
    request = object.__new__(MapleParser).write("hello", IGN, channel="party")

    assert request.kwargs["keys"] == {**DEFAULT_CHAT_KEYS, "party": "p"}


def test_startup_with_no_section_uses_the_defaults(keybindings: Path) -> None:
    keybindings.write_text("[Someone else]\n")

    assert writing.startup_chat_keys(IGN) == DEFAULT_CHAT_KEYS
    assert writing.started_chat_keys(IGN) == DEFAULT_CHAT_KEYS


@pytest.mark.parametrize(
    ("raw", "error"),
    [("['party']", TypeError), ("{'shout': 'p'}", ValueError), ("{'party", ValueError)],
)
def test_a_malformed_binding_raises_at_startup(
    keybindings: Path, raw: str, error: type[Exception]
) -> None:
    keybindings.write_text(f"[{IGN}]\nChat Keys = {raw}\n")

    with pytest.raises(error):
        writing.startup_chat_keys(IGN)
    assert writing.started_chat_keys(IGN) is None


def test_a_bot_with_a_malformed_binding_refuses_to_start(keybindings: Path) -> None:
    keybindings.write_text(f"[{IGN}]\nChat Keys = {{'shout': 'p'}}\n")

    with pytest.raises(StartupRefused, match=f"Refusing to start {IGN}.*shout"):
        TrainingBot(IGN, {}, character_class="Bishop")  # pyright: ignore[reportArgumentType]
