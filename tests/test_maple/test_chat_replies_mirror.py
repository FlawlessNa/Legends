"""The Discord mirror formats one exchange, and sends it through `send`."""

from botting.communications.messages import QuietMessage
from maple.chat_replies.addressing import Address
from maple.chat_replies.conversation import Burst, Entry, EntryState
from maple.chat_replies.mirror import format_exchange, mirror
from maple.chat_replies.relay import Failed, Reply, Silent
from maple.screen.chat import ChatKind


def _burst(
    kind: ChatKind, speaker: str, messages: list[str], address: Address
) -> Burst:
    entries = tuple(
        Entry(i, kind, speaker, m, False, 0.0, EntryState.PENDING, address)
        for i, m in enumerate(messages, 1)
    )
    return Burst(speaker, kind, address, entries)


def test_a_reply_reads_line_arrow_reply() -> None:
    burst = _burst(ChatKind.WHISPER, "Bob", ["hi u there?"], Address.MUST)

    assert format_exchange(burst, Reply("ya")) == "[whisper] Bob: hi u there? → ya"


def test_silence_is_shown() -> None:
    burst = _burst(ChatKind.GENERAL, "Ann", ["lol"], Address.JUDGE)

    assert format_exchange(burst, Silent()) == "[general] Ann: lol → (silent)"


def test_a_failure_is_shown_with_its_reason() -> None:
    burst = _burst(ChatKind.PARTY, "Ann", ["hey"], Address.MUST)

    assert (
        format_exchange(burst, Failed("model timeout"))
        == "[party] Ann: hey → (no reply: model timeout)"
    )


def test_a_burst_of_several_lines_is_one_exchange() -> None:
    burst = _burst(ChatKind.WHISPER, "Bob", ["hi", "u there?"], Address.MUST)

    assert format_exchange(burst, Reply("ya")) == "[whisper] Bob: hi / u there? → ya"


def test_a_gm_exchange_rings_and_others_do_not() -> None:
    gm = _burst(ChatKind.GM, "Zed", ["are you botting?"], Address.GM)
    other = _burst(ChatKind.WHISPER, "Bob", ["hi"], Address.MUST)

    assert format_exchange(gm, Reply("no"), "<@42>").startswith("<@42> [gm] Zed:")
    assert not format_exchange(other, Reply("hey"), "<@42>").startswith("<@")


def test_a_gm_exchange_without_a_mention_still_reads() -> None:
    gm = _burst(ChatKind.GM, "Zed", ["hello"], Address.GM)

    assert format_exchange(gm, Reply("hi")) == "[gm] Zed: hello → hi"


def test_mirror_sends_the_formatted_exchange() -> None:
    sent: list[str] = []
    burst = _burst(ChatKind.WHISPER, "Bob", ["hi"], Address.MUST)

    mirror(sent.append, burst, Reply("ya"))

    assert sent == ["[whisper] Bob: hi → ya"]


def test_a_gm_exchange_is_posted_with_the_mention_and_others_quietly() -> None:
    sent: list[str] = []
    gm = _burst(ChatKind.GM, "Zed", ["hello"], Address.GM)
    other = _burst(ChatKind.WHISPER, "Bob", ["hi"], Address.MUST)

    mirror(sent.append, gm, Reply("hi"), "<@42>")
    mirror(sent.append, other, Reply("ya"), "<@42>")

    assert not isinstance(sent[0], QuietMessage)
    assert sent[0].startswith("<@42> ")
    assert isinstance(sent[1], QuietMessage)
    assert "<@" not in sent[1]
