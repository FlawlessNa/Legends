"""
`toolkit/chat_mirror.py`: the pieces that need no client. The speaker split and
the line format over a table of lines, the states it says once, the refusal of a
`--save-unread` inside the repo, and the loop over synthetic frames, so each new
line is printed exactly once. All names here are invented.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest

from botting.screen import Frame, Reading, Status
from maple.screen.chat import ChatKind, ChatLine
from tests.test_maple.test_screen_chat import (
    PINK_BAND,
    POINT,
    TEAL_BAND,
    WINDOW,
    YELLOW,
    Row,
    chat_frame,
    draw_chat,
    frame,
    reader,
    screen,
)
from toolkit import chat_mirror
from toolkit.chat_mirror import (
    StateReporter,
    format_line,
    is_unread,
    mirror,
    refuse_inside_repo,
    save_unread,
    split_speaker,
)

IMAGE = np.zeros((16, 541, 3), np.uint8)
NO_GLYPHS = "<unreadable> (no glyphs for this kind yet)"


def line(kind: ChatKind, text: str | None) -> ChatLine:
    return ChatLine(kind, IMAGE, text, 0)


@pytest.mark.parametrize(
    ("text", "speaker", "message"),
    [
        ("Rina : anyone selling?", "Rina", "anyone selling?"),
        ("Rina : a : b", "Rina", "a : b"),
        ("Rina : ", "Rina", ""),
        ("no speaker here", "?", "no speaker here"),
        (" : orphan", "?", " : orphan"),
        ("two words : x", "?", "two words : x"),
        (None, "?", None),
    ],
)
def test_the_speaker_is_split_off_only_where_the_format_shows_it(
    text: str | None, speaker: str, message: str | None
) -> None:
    assert split_speaker(text) == (speaker, message)


@pytest.mark.parametrize(
    ("kind", "text", "printed"),
    [
        (ChatKind.GENERAL, "Rina : hi!", "12:03:41  [general]  Rina: hi!"),
        (ChatKind.GENERAL, "just text", "12:03:41  [general]  ?: just text"),
        (
            ChatKind.GENERAL,
            None,
            "12:03:41  [general]  ?: <unreadable> (a character no glyph explains)",
        ),
        (ChatKind.UNKNOWN, None, f"12:03:41  [unknown]  ?: {NO_GLYPHS}"),
        (ChatKind.MEGAPHONE, None, f"12:03:41  [megaphone]  ?: {NO_GLYPHS}"),
        (ChatKind.SYSTEM, None, f"12:03:41  [system]  ?: {NO_GLYPHS}"),
        (ChatKind.WHISPER, "Kai : psst", "12:03:41  [whisper]  Kai: psst"),
        (ChatKind.PARTY, None, f"12:03:41  [party]  ?: {NO_GLYPHS}"),
        (ChatKind.BUDDY, None, f"12:03:41  [buddy]  ?: {NO_GLYPHS}"),
        (ChatKind.GM, None, f"12:03:41  [gm]  ?: {NO_GLYPHS}"),
    ],
)
def test_every_kind_prints_as_time_kind_speaker_text(
    kind: ChatKind, text: str | None, printed: str
) -> None:
    assert format_line(line(kind, text), "12:03:41") == printed


def test_a_line_is_unread_when_unknown_or_without_text() -> None:
    assert is_unread(line(ChatKind.UNKNOWN, "x"))
    assert is_unread(line(ChatKind.GENERAL, None))
    assert not is_unread(line(ChatKind.GENERAL, "Rina : hi"))


# --- states ---------------------------------------------------------------


def reading(status: Status, detail: str = "") -> Reading[list[ChatLine]]:
    if status is Status.READ:
        return Reading.read([], 0.0, detail)
    return Reading(None, status, 0.0, detail)


def test_a_state_is_said_once_and_again_when_the_chat_is_back() -> None:
    states = StateReporter()
    hidden = reading(Status.ABSENT, "chat log hidden")
    assert states.update(reading(Status.READ)) is None
    first = states.update(hidden)
    assert first is not None
    assert "chat log hidden" in first
    assert states.update(hidden) is None
    assert states.update(hidden) is None
    assert states.update(reading(Status.READ)) == "the chat is readable again"
    assert states.update(reading(Status.READ)) is None
    assert states.update(hidden) is not None


def test_a_change_of_state_is_said_again() -> None:
    states = StateReporter()
    assert states.update(reading(Status.ABSENT, "chat log hidden")) is not None
    assert states.update(reading(Status.ABSENT, "chat not found")) is not None
    assert states.update(reading(Status.COVERED, "something at y=10")) is not None


def test_a_covered_row_moving_is_the_same_state() -> None:
    states = StateReporter()
    assert states.update(reading(Status.COVERED, "over the row at y=10")) is not None
    assert states.update(reading(Status.COVERED, "over the row at y=26")) is None


# --- --save-unread --------------------------------------------------------


def test_a_save_folder_inside_the_repo_is_refused() -> None:
    with pytest.raises(ValueError, match="inside the repository"):
        refuse_inside_repo(chat_mirror.REPO / "data" / "rows")
    with pytest.raises(ValueError, match="inside the repository"):
        refuse_inside_repo(chat_mirror.REPO)


def test_a_save_folder_outside_the_repo_is_accepted(tmp_path: Path) -> None:
    refuse_inside_repo(tmp_path / "rows", repo=tmp_path / "repo")


def test_main_refuses_a_save_folder_inside_the_repo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    inside = chat_mirror.REPO / "rows"
    assert chat_mirror.main(["--save-unread", str(inside)]) == 2
    assert "inside the repository" in capsys.readouterr().err
    assert not inside.exists()


def test_an_unread_row_is_saved_named_by_time_and_kind(tmp_path: Path) -> None:
    path = save_unread(line(ChatKind.UNKNOWN, None), tmp_path / "rows", "12:03:41", 3)
    assert path.name == "120341-0003-unknown.png"
    saved = cv2.imread(str(path))
    assert saved is not None
    assert saved.shape == IMAGE.shape


# --- the loop -------------------------------------------------------------


def fixed_now() -> datetime:
    return datetime(2026, 11, 15, 12, 3, 41, tzinfo=UTC)


def run(frames: list[Frame], save_to: Path | None = None) -> tuple[list[str], int]:
    out: list[str] = []
    feed: Iterator[Frame] = iter(frames)
    printed = mirror(
        lambda: next(feed),
        reader(),
        save_to=save_to,
        out=out.append,
        now=fixed_now,
        sleep=lambda _: None,
        reads=len(frames),
    )
    return out, printed


def test_each_new_line_is_printed_exactly_once_in_order() -> None:
    log = [Row(text="H"), Row(text="i"), Row(text="Hi"), Row(text="Hi!")]
    arrived = [Row(text="Hi!"), Row(TEAL_BAND, "i")]
    out, printed = run(
        [
            chat_frame(log),
            chat_frame(log),
            chat_frame(log[2:] + arrived),
            chat_frame(log[2:] + arrived),
        ]
    )
    assert printed == 6
    assert out == [
        "12:03:41  [general]  ?: H",
        "12:03:41  [general]  ?: i",
        "12:03:41  [general]  ?: Hi",
        "12:03:41  [general]  ?: Hi!",
        "12:03:41  [general]  ?: Hi!",
        f"12:03:41  [megaphone]  ?: {NO_GLYPHS}",
    ]


def test_hidden_and_covered_are_said_once_and_nothing_is_reprinted() -> None:
    log = [Row(text="Hi")] * 2 + [Row(text="i"), Row(text="H")]
    hidden = screen()
    draw_chat(hidden, log, hidden=True)
    covered = screen()
    draw_chat(covered, log)
    covered[POINT[1] - 30 : POINT[1] - 10, POINT[0] + 100 : POINT[0] + 300] = WINDOW
    out, printed = run(
        [
            chat_frame(log),
            frame(hidden),
            frame(hidden),
            frame(covered),
            frame(covered),
            chat_frame(log),
        ]
    )
    said = [o.split("** ")[1].split(" (")[0] for o in out if "**" in o]
    assert said == [
        "cannot read the chat",
        "cannot read the chat",
        "the chat is readable again",
    ]
    assert printed == 4  # the first read's lines; nothing repeated after


def test_unread_lines_are_saved_when_asked(tmp_path: Path) -> None:
    log = [Row(text="Hi"), Row(PINK_BAND, "H"), Row(text="i", colour=YELLOW)]
    out, _ = run([chat_frame(log)], save_to=tmp_path)
    assert len(out) == 3
    # A megaphone and a system line have no text, so they are unread.
    assert sorted(p.name.split("-", 2)[2] for p in tmp_path.glob("*.png")) == [
        "megaphone.png",
        "system.png",
    ]
