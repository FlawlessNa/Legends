"""
Mirror the in-game chat to the console, to see where the chat reader is right.

Chat mirror (#549, epic #302): while it runs, each new chat line is printed once,
as it appears, with its time, the reader's kind, who wrote it and what it says:

    12:03:41  [general]  Maple_Rina: anyone selling a scroll?
    12:03:44  [unknown]  ?: <unreadable>

so the maintainer can put the console beside the game window and compare. It
shows `maple/screen/chat.py`'s `ChatReader` as it is, including where it fails:
the kind is the reader's (`unknown` is printed as `unknown`: a colour of row it
cannot tell yet, such as party, buddy or GM), the speaker and message are
`ChatLine.speaker` and `ChatLine.message`, and when the text is `None` the line
prints `<unreadable>`.

**It sends no keys, no clicks and no input, ever.** It copies the client's
pixels (`botting.screen`'s Desktop Duplication, as the bot does) and prints. It
imports nothing that sends input.

    python -m toolkit.chat_mirror
    python -m toolkit.chat_mirror --interval 0.5
    python -m toolkit.chat_mirror --save-unread D:/Games/ChatRows

**What it needs.** The MapleStory client open (the one `configs/game.ini`
names) with the chat log showing, the game data store (`configs/game_data.ini`),
and the chat's glyph set from `python -m toolkit.harvest_glyphs`. Stop it with
Ctrl+C.

**The speaker** is the reader's, split by each kind's format, the time the
client may put first left out (#482): a general line's `Name : message`, an
outgoing whisper's `Name<< message`, printed `to Name`. Where the reader gives
none (a row that doesn't fit, the rest of a wrapped line, a notice), the
speaker is `?` and the whole text is printed, never a guess. Party, buddy,
megaphone and GM lines have no glyphs yet, so their text is `<unreadable>`.

**What it cannot see**, it says once: when the chat log is hidden, when
something covers it (`COVERED`), when the chat is not found, or when the frame
is not the client's. It says so again when the chat is back; a repeat of the same
state prints nothing.

**`--save-unread DIR`** (off by default) saves the row image of every line it
could not fully read (`unknown` kind, or no text) into `DIR` as PNGs named by time
and kind, to build the frame sets #315 needs. The images show other players'
names: `DIR` must be **outside the repository and is never committed**, and the
tool refuses a `DIR` inside it.

**First read.** The reader returns every line showing on its first read, so the
lines already in the log when it starts are printed first.

**During a Session.** It runs in its own process with its own Desktop
Duplication, and takes CPU from the bot's process. It has not been run beside a
Session.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Final, Protocol

import cv2

from botting.screen import Frame, Reading, Status
from maple.screen.chat import TEXT_READ, ChatKind, ChatLine

REPO = Path(__file__).resolve().parents[1]

DEFAULT_INTERVAL: Final = 0.25
"""Seconds between reads. Each read is of the whole log, and a line stays on
screen for much longer."""

UNREADABLE: Final = "<unreadable>"
UNKNOWN_SPEAKER: Final = "?"

_NO_GLYPH: Final = " (a character no glyph explains)"
_NO_GLYPHS_YET: Final = " (no glyphs for this kind yet)"


class ChatSource(Protocol):
    """The part of `ChatReader` used here."""

    def read(self, frame: Frame) -> Reading[list[ChatLine]]: ...


# ------------------------------------------------------------------ one line


def speaker_and_message(line: ChatLine) -> tuple[str, str | None]:
    """
    Who wrote `line` and what, as printed: the reader's speaker and message
    (`to <speaker>` for an outgoing whisper); `?` and the whole text when the
    reader split none.
    """
    if line.speaker is None or line.message is None:
        return UNKNOWN_SPEAKER, line.text
    if line.outgoing and line.kind is ChatKind.WHISPER:
        return f"to {line.speaker}", line.message
    return line.speaker, line.message


def format_line(line: ChatLine, stamp: str) -> str:
    """`HH:MM:SS  [kind]  IGN: text`, as printed for `line`."""
    speaker, message = speaker_and_message(line)
    if message is None:
        note = _NO_GLYPH if line.kind in TEXT_READ else _NO_GLYPHS_YET
        message = UNREADABLE + note
    return f"{stamp}  [{line.kind.value}]  {speaker}: {message}"


def is_unread(line: ChatLine) -> bool:
    """Whether the reader could not fully read `line`."""
    return line.kind is ChatKind.UNKNOWN or line.text is None


# ------------------------------------------------------------------- states


class StateReporter:
    """
    Says what the mirror cannot see, once, and when it is back.

    A state is the reading's status (and its detail, except for `COVERED`,
    whose detail names the row covered and moves with the window).
    """

    def __init__(self) -> None:
        self._state: tuple[Status, str] | None = None

    def update(self, reading: Reading[list[ChatLine]]) -> str | None:
        """The message to print for `reading`, or `None` when the state is the
        one already reported."""
        if reading.status is Status.READ:
            was, self._state = self._state, None
            return "the chat is readable again" if was is not None else None
        detail = "" if reading.status is Status.COVERED else reading.detail
        state = (reading.status, detail)
        if state == self._state:
            return None
        self._state = state
        why = f": {reading.detail}" if reading.detail else ""
        return f"cannot read the chat ({reading.status.value}){why}"


# --------------------------------------------------------------- save-unread


def refuse_inside_repo(directory: Path, repo: Path = REPO) -> None:
    """
    :raises ValueError: `directory` is inside `repo`: the rows show other
        players' names and must not be committed.
    """
    if directory.resolve().is_relative_to(repo.resolve()):
        raise ValueError(
            f"--save-unread {directory} is inside the repository ({repo}): the "
            "images show other players' names, so use a folder outside it"
        )


def save_unread(line: ChatLine, directory: Path, stamp: str, n: int) -> Path:
    """Write `line`'s row image into `directory` as `<stamp>-<n>-<kind>.png`."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stamp.replace(':', '')}-{n:04d}-{line.kind.value}.png"
    if not cv2.imwrite(str(path), line.image):
        raise OSError(f"can't write {path}")
    return path


# ---------------------------------------------------------------------- loop


def mirror(
    grab: Callable[[], Frame],
    reader: ChatSource,
    *,
    interval: float = DEFAULT_INTERVAL,
    save_to: Path | None = None,
    out: Callable[[str], None] = print,
    now: Callable[[], datetime] = datetime.now,
    sleep: Callable[[float], None] = time.sleep,
    reads: int | None = None,
) -> int:
    """
    Print each new line `reader` returns from the frames `grab` gives, and say
    when the chat cannot be seen.

    :param reads: Stop after this many frames (`None`: run until interrupted).
    :return: The number of lines printed.
    """
    states = StateReporter()
    printed = saved = 0
    count = 0
    while reads is None or count < reads:
        frame = grab()
        if not frame.fresh:  # the last copy again, or none at all
            sleep(0.005)
            continue
        count += 1
        reading = reader.read(frame)
        message = states.update(reading)
        if message is not None:
            out(f"{now():%H:%M:%S}  ** {message}")
        for line in reading.value or []:
            stamp = f"{now():%H:%M:%S}"
            out(format_line(line, stamp))
            printed += 1
            if save_to is not None and is_unread(line):
                saved += 1
                save_unread(line, save_to, stamp, saved)
        if reads is None or count < reads:
            sleep(interval)
    return printed


# ---------------------------------------------------------------------- main


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m toolkit.chat_mirror",
        description="Print each new in-game chat line with its kind, speaker and "
        "text, to check the chat reader against the window. Sends no input.",
    )
    p.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL,
        help=f"seconds between reads (default {DEFAULT_INTERVAL})",
    )  # fmt: skip
    p.add_argument(
        "--save-unread", type=Path, metavar="DIR",
        help="save the row image of every line not fully read (unknown kind or no "
        "text) into DIR, named by time and kind. The images show other players' "
        "names: DIR must be OUTSIDE the repository, never committed; a DIR inside "
        "it is refused.",
    )  # fmt: skip
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.save_unread is not None:
        try:
            refuse_inside_repo(args.save_unread)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 2

    from botting.screen import frame_source
    from maple.screen.chat import CHAT, ChatReader
    from maple.screen.client import find_client
    from maple.screen.locator import FrameCheck
    from maple.screen.sprites import FRAME_CHECK, Profile, load_reader_sprites

    handle = find_client()
    source = frame_source()
    sprites = load_reader_sprites([FRAME_CHECK, CHAT], Profile(job=""))
    reader = ChatReader(sprites, FrameCheck(sprites))
    try:
        mirror(
            lambda: source.grab(handle),
            reader,
            interval=args.interval,
            save_to=args.save_unread,
        )
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
