"""
`Conversation`: every line appended once, our own lines known as ours, and each
line to answer leaving `pending` exactly once (#461).

The names and messages are invented.
"""

from dataclasses import dataclass

import pytest

from maple.chat_replies.addressing import Address
from maple.chat_replies.conversation import (
    ECHO_WINDOW,
    UNREAD,
    Burst,
    Conversation,
    EntryState,
)
from maple.screen.chat import ChatKind

IGN = "Mapler"


@dataclass(frozen=True)
class Line:
    kind: ChatKind
    speaker: str | None
    message: str | None
    outgoing: bool = False
    text: str | None = None
    continues: bool = False


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def conversation(clock: Clock) -> Conversation:
    return Conversation(IGN, clock=clock)


def whisper(speaker: str, message: str | None, *, outgoing: bool = False) -> Line:
    return Line(ChatKind.WHISPER, speaker, message, outgoing)


def general(speaker: str | None, message: str | None) -> Line:
    return Line(ChatKind.GENERAL, speaker, message)


def rest(text: str, kind: ChatKind = ChatKind.GENERAL) -> Line:
    """A row that continues the line above, which wrapped."""
    return Line(kind, None, None, text=text, continues=True)


# Appending.


def test_entries_are_numbered_from_one_and_stamped_by_the_clock(
    conversation: Conversation, clock: Clock
) -> None:
    first = conversation.append(general("Bob", "hi all"), Address.JUDGE)
    clock.now = 103.5
    second = conversation.append(whisper("Ann", "yo"), Address.MUST)

    assert first is not None
    assert second is not None
    assert (first.seq, first.seen_at) == (1, 100.0)
    assert (second.seq, second.seen_at) == (2, 103.5)
    assert (second.kind, second.speaker, second.message) == (
        ChatKind.WHISPER,
        "Ann",
        "yo",
    )
    assert conversation.recent() == [first, second]


@pytest.mark.parametrize(
    ("address", "state"),
    [
        (Address.MUST, EntryState.PENDING),
        (Address.GM, EntryState.PENDING),
        (Address.JUDGE, EntryState.PENDING),
        (Address.IGNORE, EntryState.CONTEXT),
    ],
)
def test_an_entry_starts_pending_unless_ignored(
    conversation: Conversation, address: Address, state: EntryState
) -> None:
    entry = conversation.append(whisper("Bob", "hi"), address)

    assert entry is not None
    assert entry.state is state
    assert entry.address is address


@pytest.mark.parametrize("address", [Address.MUST, Address.GM, Address.JUDGE])
def test_every_entry_appended_while_replies_are_off_is_context(
    conversation: Conversation, address: Address
) -> None:
    entry = conversation.append(whisper("Bob", "hi"), address, replies_on=False)

    assert entry is not None
    assert entry.state is EntryState.CONTEXT
    assert conversation.pending() == []
    # Lines that arrived while off are never answered late.
    conversation.append(general("Ann", "lol"), Address.JUDGE)
    assert [b.speaker for b in conversation.pending()] == ["Ann"]


@pytest.mark.parametrize(
    "kind", [ChatKind.MEGAPHONE, ChatKind.SYSTEM, ChatKind.UNKNOWN]
)
def test_megaphone_system_and_unknown_lines_are_never_appended(
    conversation: Conversation, kind: ChatKind
) -> None:
    assert conversation.append(Line(kind, "Bob", "buying stuff"), Address.MUST) is None
    assert conversation.recent() == []
    following = conversation.append(general("Ann", "hey"), Address.JUDGE)
    assert following is not None
    assert following.seq == 1


# Ours.


def test_an_outgoing_line_is_ours_and_never_pending(conversation: Conversation) -> None:
    entry = conversation.append(whisper("Bob", "ya", outgoing=True), Address.MUST)

    assert entry is not None
    assert entry.ours
    assert entry.state is EntryState.CONTEXT
    assert conversation.pending() == []


def test_a_line_whose_speaker_is_the_ign_is_ours(conversation: Conversation) -> None:
    entry = conversation.append(general("mapler", "brb"), Address.JUDGE)

    assert entry is not None
    assert entry.ours
    assert conversation.pending() == []


def test_the_echo_of_a_reply_is_ours_even_with_its_speaker_misread(
    conversation: Conversation, clock: Clock
) -> None:
    conversation.expect_echo(" sry map's full ", ChatKind.GENERAL)
    clock.now += 2.0
    # The speaker read wrong, and one character unread.
    echo = general("Mapier", f"sry map{UNREAD}s full")
    entry = conversation.append(echo, Address.JUDGE)

    assert entry is not None
    assert entry.ours
    assert entry.state is EntryState.CONTEXT
    assert conversation.pending() == []


@pytest.mark.parametrize(
    "read",
    ["IoI ty", f"I{UNREAD}I ty", f"lol {UNREAD}y"],
    ids=["l read as I", "and one unread", "one unread"],
)
def test_the_echo_of_a_reply_is_ours_as_read(
    conversation: Conversation, read: str
) -> None:
    conversation.expect_echo("lol ty", ChatKind.GENERAL)

    entry = conversation.append(general("Mapier", read), Address.JUDGE)

    assert entry is not None
    assert entry.ours


@pytest.mark.parametrize(
    ("sent", "read"),
    [
        ("brb gtg", f"{UNREAD * 3} {UNREAD}{UNREAD}g"),
        ("ya", f"{UNREAD}a"),
        ("brb gtg", "brb gtG"),
    ],
    ids=["mostly unread", "half of two", "case"],
)
def test_a_line_with_too_few_letters_read_is_not_our_echo(
    conversation: Conversation, sent: str, read: str
) -> None:
    conversation.expect_echo(sent, ChatKind.GENERAL)

    entry = conversation.append(general("Bob", read), Address.JUDGE)

    assert entry is not None
    assert not entry.ours
    assert entry.state is EntryState.PENDING


@pytest.mark.parametrize("speaker", ["MapIer", f"Map{UNREAD}er"])
def test_a_speaker_read_as_the_ign_is_ours(
    conversation: Conversation, speaker: str
) -> None:
    entry = conversation.append(general(speaker, "brb"), Address.JUDGE)

    assert entry is not None
    assert entry.ours


def test_a_speaker_with_too_few_letters_read_is_not_ours(
    conversation: Conversation,
) -> None:
    entry = conversation.append(whisper(f"M{UNREAD * 5}", "hi"), Address.MUST)

    assert entry is not None
    assert not entry.ours
    assert entry.state is EntryState.PENDING


def test_an_echo_is_recognised_up_to_ten_seconds_and_not_after(
    conversation: Conversation, clock: Clock
) -> None:
    conversation.expect_echo("ya", ChatKind.WHISPER)
    conversation.expect_echo("np", ChatKind.WHISPER)
    clock.now += ECHO_WINDOW
    on_time = conversation.append(whisper("Bob", "ya"), Address.MUST)
    clock.now += 0.1
    late = conversation.append(whisper("Bob", "np"), Address.MUST)

    assert on_time is not None
    assert on_time.ours
    assert late is not None
    assert not late.ours
    assert late.state is EntryState.PENDING


@pytest.mark.parametrize(
    "line",
    [
        general("Bob", "ya"),  # Another channel.
        whisper("Bob", "yaa"),  # Another length.
        whisper("Bob", "yo"),  # Another character, read.
        whisper("Bob", None),  # No message split.
    ],
)
def test_a_line_that_does_not_match_the_echo_is_not_ours(
    conversation: Conversation, line: Line
) -> None:
    conversation.expect_echo("ya", ChatKind.WHISPER)

    entry = conversation.append(line, Address.MUST)

    assert entry is not None
    assert not entry.ours


def test_an_echo_makes_one_line_ours(conversation: Conversation) -> None:
    conversation.expect_echo("hi", ChatKind.WHISPER)

    echo = conversation.append(whisper("Bob", "hi"), Address.MUST)
    repeated = conversation.append(whisper("Bob", "hi"), Address.MUST)

    assert echo is not None
    assert echo.ours
    assert repeated is not None
    assert not repeated.ours


def test_an_outgoing_line_takes_its_echo(conversation: Conversation) -> None:
    # Our line, read as ours, uses up its echo: a player repeating it isn't us.
    conversation.expect_echo("gl", ChatKind.GENERAL)
    conversation.append(
        Line(ChatKind.GENERAL, IGN, "gl", outgoing=True), Address.IGNORE
    )

    repeated = conversation.append(general("Bob", "gl"), Address.JUDGE)

    assert repeated is not None
    assert not repeated.ours


# Bursts.


def test_pending_groups_by_player_and_channel_oldest_first(
    conversation: Conversation,
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    conversation.append(general("Ann", "lol"), Address.JUDGE)
    conversation.append(whisper("Bob", "u there?"), Address.MUST)
    conversation.append(general("Bob", "anyone?"), Address.JUDGE)
    conversation.append(general("Ann", "mapler hi"), Address.MUST)
    conversation.append(general("Cid", "brb"), Address.IGNORE)

    bursts = conversation.pending()

    assert [
        (b.speaker, b.channel, b.address, [e.seq for e in b.entries]) for b in bursts
    ] == [
        ("Bob", ChatKind.WHISPER, Address.MUST, [1, 3]),
        ("Ann", ChatKind.GENERAL, Address.MUST, [2, 5]),
        ("Bob", ChatKind.GENERAL, Address.JUDGE, [4]),
    ]


def test_a_burst_groups_a_speaker_whatever_its_case(
    conversation: Conversation,
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    conversation.append(whisper("bob", "u there?"), Address.MUST)
    conversation.append(whisper("BOB", "hello??"), Address.MUST)

    [burst] = conversation.pending()

    assert (burst.speaker, [e.seq for e in burst.entries]) == ("Bob", [1, 2, 3])


def test_a_burst_groups_a_speaker_read_in_part_and_names_the_best_read(
    conversation: Conversation,
) -> None:
    conversation.append(whisper(f"B{UNREAD}b", "hi"), Address.MUST)
    conversation.append(whisper("Bob", "u there?"), Address.MUST)
    conversation.append(whisper("Bo", "hey"), Address.MUST)

    first, other = conversation.pending()

    assert (first.speaker, [e.seq for e in first.entries]) == ("Bob", [1, 2])
    assert (other.speaker, [e.seq for e in other.entries]) == ("Bo", [3])


def test_a_burst_takes_the_gm_address_over_must(conversation: Conversation) -> None:
    conversation.append(Line(ChatKind.GM, "Gee", "hello"), Address.GM)
    conversation.append(Line(ChatKind.GM, "Gee", "mapler?"), Address.MUST)

    [burst] = conversation.pending()

    assert burst.address is Address.GM


# Wrapped lines.


def test_a_row_that_continues_a_line_is_joined_to_it(
    conversation: Conversation,
) -> None:
    head = conversation.append(general("Bob", "hey whats"), Address.JUDGE)
    joined = conversation.append(rest(" up Mapler? "), Address.MUST)

    assert head is not None
    assert joined is not None
    assert (joined.seq, joined.speaker, joined.message) == (
        1,
        "Bob",
        "hey whats up Mapler?",
    )
    assert joined.address is Address.MUST
    assert conversation.recent() == [joined]
    [burst] = conversation.pending()
    assert (burst.address, burst.entries) == (Address.MUST, (joined,))


def test_a_row_that_continues_a_line_keeps_its_stronger_address(
    conversation: Conversation,
) -> None:
    conversation.append(Line(ChatKind.GENERAL, "Gee", "hello"), Address.GM)

    joined = conversation.append(rest("there"), Address.IGNORE)

    assert joined is not None
    assert (joined.message, joined.address) == ("hello there", Address.GM)
    assert joined.state is EntryState.PENDING


def test_a_line_ignored_on_its_first_row_is_answered_when_the_next_names_us(
    conversation: Conversation,
) -> None:
    conversation.append(general("Bob", "hey"), Address.IGNORE)

    joined = conversation.append(rest("Mapler"), Address.MUST)

    assert joined is not None
    assert joined.state is EntryState.PENDING


def test_a_row_that_continues_a_line_appended_while_replies_are_off_stays_context(
    conversation: Conversation,
) -> None:
    conversation.append(general("Bob", "hey"), Address.IGNORE, replies_on=False)

    joined = conversation.append(rest("Mapler"), Address.MUST, replies_on=False)

    assert joined is not None
    assert joined.state is EntryState.CONTEXT


def test_a_row_that_continues_our_line_is_ours(conversation: Conversation) -> None:
    conversation.append(general(IGN, "sry map's"), Address.IGNORE)

    joined = conversation.append(rest("full Mapler"), Address.MUST)

    assert joined is not None
    assert joined.ours
    assert (joined.address, joined.state) == (Address.IGNORE, EntryState.CONTEXT)
    assert conversation.pending() == []


def test_a_reply_that_wraps_is_our_echo_once_joined(
    conversation: Conversation,
) -> None:
    conversation.expect_echo("sry map's full, maybe later", ChatKind.GENERAL)
    head = conversation.append(general("Mapier", "sry map's full,"), Address.JUDGE)
    assert head is not None
    assert not head.ours

    joined = conversation.append(rest("maybe later"), Address.IGNORE)

    assert joined is not None
    assert joined.ours
    assert joined.state is EntryState.CONTEXT
    assert conversation.pending() == []


@pytest.mark.parametrize(
    "above",
    [None, whisper("Bob", "hi")],
    ids=["nothing above", "another kind above"],
)
def test_a_row_that_continues_nothing_is_appended_as_it_is(
    conversation: Conversation, above: Line | None
) -> None:
    if above is not None:
        conversation.append(above, Address.MUST)

    entry = conversation.append(rest("whats up"), Address.IGNORE)

    assert entry is not None
    assert (entry.seq, entry.speaker, entry.message) == (
        len(conversation.recent()),
        None,
        None,
    )
    assert entry.state is EntryState.CONTEXT


# Resolving.


@pytest.mark.parametrize(
    "state", [EntryState.ANSWERED, EntryState.SILENT, EntryState.FAILED]
)
def test_resolve_moves_the_burst_out_of_pending(
    conversation: Conversation, state: EntryState
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    conversation.append(whisper("Bob", "u there?"), Address.MUST)
    [burst] = conversation.pending()

    conversation.resolve(burst, state)

    assert conversation.pending() == []
    assert [e.state for e in conversation.recent()] == [state, state]


def test_lines_arriving_after_the_burst_was_taken_stay_pending(
    conversation: Conversation,
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    [burst] = conversation.pending()
    conversation.append(whisper("Bob", "hello??"), Address.MUST)

    conversation.resolve(burst, EntryState.ANSWERED)

    [left] = conversation.pending()
    assert [e.seq for e in left.entries] == [2]


def test_an_entry_leaves_pending_exactly_once(conversation: Conversation) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    [burst] = conversation.pending()
    conversation.resolve(burst, EntryState.ANSWERED)

    with pytest.raises(ValueError, match="entry 1 already left pending"):
        conversation.resolve(burst, EntryState.FAILED)

    assert conversation.recent()[0].state is EntryState.ANSWERED


def test_a_burst_with_one_resolved_entry_changes_nothing(
    conversation: Conversation,
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    [first] = conversation.pending()
    conversation.resolve(first, EntryState.ANSWERED)
    conversation.append(whisper("Bob", "hello??"), Address.MUST)
    [second] = conversation.pending()
    both = Burst("Bob", ChatKind.WHISPER, Address.MUST, first.entries + second.entries)

    with pytest.raises(ValueError, match="entry 1"):
        conversation.resolve(both, EntryState.SILENT)

    assert [e.state for e in conversation.recent()] == [
        EntryState.ANSWERED,
        EntryState.PENDING,
    ]


@pytest.mark.parametrize("state", [EntryState.PENDING, EntryState.CONTEXT])
def test_resolve_refuses_a_state_that_is_not_a_resolution(
    conversation: Conversation, state: EntryState
) -> None:
    conversation.append(whisper("Bob", "hi"), Address.MUST)
    [burst] = conversation.pending()

    with pytest.raises(ValueError, match="not a resolution"):
        conversation.resolve(burst, state)

    assert conversation.recent()[0].state is EntryState.PENDING


# What a request carries.


def test_recent_is_the_last_fifty_entries_by_default(
    conversation: Conversation,
) -> None:
    for i in range(60):
        conversation.append(general("Bob", f"line {i}"), Address.JUDGE)

    assert [e.seq for e in conversation.recent()] == list(range(11, 61))
    assert [e.seq for e in conversation.recent(3)] == [58, 59, 60]
    assert conversation.recent(0) == []
