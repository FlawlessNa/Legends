"""
`controller.write` and the human typing pace.

What reaches the client is recorded at `SendInput` and `PostMessage`
(`tests/sent_input.py`); everything above them runs as it does live.
"""

import itertools
import pickle
import random
from collections.abc import Iterator
from typing import Any

import pytest

from botting.controller import DELAY, TypingPace, high_level, write
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger
from tests import sent_input
from tests.sent_input import SentInput

HANDLE = 1234
SEED = 460
MESSAGE = "Hi u there?"


@pytest.fixture(autouse=True)
def reset_ledger() -> Iterator[None]:
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> SentInput:
    return sent_input.install(monkeypatch, HANDLE)


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """`high_level`'s jitter draws from a generator seeded with `SEED`."""
    monkeypatch.setattr(high_level, "random", random.Random(SEED))


def _jitter(count: int) -> list[float]:
    """The delays `write` has always drawn: `DELAY`, jittered by 5%, per Step."""
    draws = random.Random(SEED)
    return [draws.uniform(0.95, 1.05) * DELAY for _ in range(count)]


# --- without a pace, write sends what it always sent ---------------------------


@pytest.mark.usefixtures("seeded")
def test_a_loud_write_types_each_character_down_then_up_at_the_jittered_delay(
    sent: SentInput,
) -> None:
    sent.run(write(HANDLE, MESSAGE, silenced=False, pace=None))

    assert sent.keys() == [
        (char, event) for char in MESSAGE for event in ("keydown", "keyup")
    ]
    assert all(step.typed for step in sent.steps)
    assert sent.sleeps == _jitter(2 * len(MESSAGE))


@pytest.mark.usefixtures("seeded")
def test_a_silent_write_posts_one_character_message_per_character(
    sent: SentInput,
) -> None:
    sent.run(write(HANDLE, MESSAGE, pace=None))

    assert sent.keys() == [(char, "char") for char in MESSAGE]
    assert sent.sleeps == _jitter(len(MESSAGE))


@pytest.mark.usefixtures("seeded")
def test_a_loud_write_with_no_delay_sends_the_whole_message_in_one_step(
    sent: SentInput,
) -> None:
    sent.run(write(HANDLE, MESSAGE, silenced=False, delay=0))

    assert sent.keys() == [
        (char, event) for char in MESSAGE for event in ("keydown", "keyup")
    ]
    assert {step.at for step in sent.steps} == {0.0}
    assert sent.sleeps == [0.0]


def test_a_write_releases_what_the_ledger_holds_first(sent: SentInput) -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    sent.run(write(HANDLE, "a", silenced=False))

    assert sent.keys()[0] == ("right", "keyup")
    assert sent.keys()[1:] == [("a", "keydown"), ("a", "keyup")]


# --- TypingPace ------------------------------------------------------------------

TEXT = "hey, map's full sry. gl! u lvling here?"


def test_every_delay_stays_within_its_documented_bounds() -> None:
    for seed in range(200):
        pace = TypingPace(rng=random.Random(seed))
        for char, delay in zip(TEXT, pace.delays(TEXT), strict=True):
            shortest, longest = pace.bounds(char)
            assert shortest <= delay <= longest


def test_the_bounds_are_those_of_180_to_260_characters_a_minute() -> None:
    pace = TypingPace()

    assert pace.bounds("a") == pytest.approx((60 / 260 * 0.75, 60 / 180 * 1.25))
    assert pace.bounds(" ") == pytest.approx(
        (60 / 260 * 0.75 * 1.5, 60 / 180 * 1.25 * 2.5)
    )


def test_one_base_rate_is_drawn_per_message() -> None:
    """
    Within a message every letter's delay is the same interval, jittered; from
    one message to the next the interval changes, across 180 to 260 a minute.
    """
    pace = TypingPace(jitter=0.0, rng=random.Random(SEED))
    intervals = []
    for _ in range(100):
        delays = pace.delays("abcdefgh")
        assert len(set(delays)) == 1
        intervals.append(delays[0])

    assert all(60 / 260 <= interval <= 60 / 180 for interval in intervals)
    assert min(intervals) < 60 / 250
    assert max(intervals) > 60 / 190


def test_each_character_is_jittered_around_the_messages_interval() -> None:
    pace = TypingPace(rng=random.Random(SEED))
    delays = pace.delays("abcdefghijklmnopqrstuvwxyz")

    assert len(set(delays)) == len(delays)
    assert max(delays) / min(delays) <= 1.25 / 0.75


@pytest.mark.parametrize("char", [" ", ".", ",", "!", "?", ";", ":"])
def test_a_space_or_punctuation_is_followed_by_a_longer_pause(char: str) -> None:
    pace = TypingPace(jitter=0.0, min_pause=2.0, max_pause=2.0)
    letter, after = pace.delays("a" + char)

    assert after == pytest.approx(2 * letter)


def test_no_pause_follows_an_apostrophe_or_a_letter() -> None:
    pace = TypingPace(jitter=0.0)
    delays = pace.delays("map's")

    assert len(set(delays)) == 1


def test_an_empty_message_has_no_delays() -> None:
    assert TypingPace().delays("") == []


@pytest.mark.parametrize(
    ("settings", "names"),
    [
        ({"min_cpm": 0.0}, "min_cpm"),
        ({"min_cpm": 300.0}, "min_cpm"),
        ({"jitter": 1.0}, "jitter"),
        ({"jitter": -0.1}, "jitter"),
        ({"min_pause": 0.5}, "min_pause"),
        ({"min_pause": 3.0}, "min_pause"),
    ],
)
def test_a_pace_that_cannot_hold_its_bounds_is_refused(
    settings: dict[str, Any], names: str
) -> None:
    with pytest.raises(ValueError, match=names):
        TypingPace(**settings)


def test_a_pace_survives_the_pipe_to_main_process() -> None:
    pace = TypingPace(rng=random.Random(SEED))

    copy = pickle.loads(pickle.dumps(pace))

    assert copy.delays(TEXT) == pace.delays(TEXT)


# --- write at a pace -------------------------------------------------------------


def _paced(message: str) -> list[float]:
    """What `TypingPace(rng=random.Random(SEED))` gives `message`."""
    return TypingPace(rng=random.Random(SEED)).delays(message)


@pytest.mark.parametrize("silenced", [False, True])
def test_a_paced_write_types_exactly_the_message(
    sent: SentInput, silenced: bool
) -> None:
    sent.run(write(HANDLE, TEXT, silenced=silenced, pace=TypingPace()))

    typed = [step.key for step in sent.steps if step.event != "keyup"]
    assert "".join(typed) == TEXT
    assert all(step.typed for step in sent.steps)


def test_a_loud_paced_write_puts_each_keydown_one_paced_delay_after_the_last(
    sent: SentInput,
) -> None:
    sent.run(
        write(HANDLE, MESSAGE, silenced=False, pace=TypingPace(rng=random.Random(SEED)))
    )

    downs = [step for step in sent.steps if step.event == "keydown"]
    gaps = [later.at - earlier.at for earlier, later in itertools.pairwise(downs)]
    assert gaps == pytest.approx(_paced(MESSAGE)[:-1])
    assert sent.keys() == [
        (char, event) for char in MESSAGE for event in ("keydown", "keyup")
    ]


def test_a_loud_paced_write_holds_each_key_for_the_jittered_delay(
    sent: SentInput,
) -> None:
    sent.run(write(HANDLE, MESSAGE, silenced=False, pace=TypingPace()))

    holds = [up.at - down.at for down, up in zip(sent.steps[::2], sent.steps[1::2])]
    assert all(0.95 * DELAY <= hold <= 1.05 * DELAY for hold in holds)


def test_a_silent_paced_write_posts_each_character_one_paced_delay_apart(
    sent: SentInput,
) -> None:
    sent.run(write(HANDLE, MESSAGE, pace=TypingPace(rng=random.Random(SEED))))

    gaps = [sent.gap_before(i) for i in range(1, len(sent.steps))]
    assert gaps == pytest.approx(_paced(MESSAGE)[:-1])


@pytest.mark.parametrize("silenced", [False, True])
def test_a_paced_write_returns_once_the_last_character_is_sent(
    sent: SentInput, silenced: bool
) -> None:
    sent.run(write(HANDLE, MESSAGE, silenced=silenced, pace=TypingPace()))

    assert sent.now == sent.steps[-1].at
