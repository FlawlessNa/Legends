"""
`MapleParser` confirms a Discord-written chat message with a picture of the
client. The picture is a `Frame`'s pixels, and a frame that can't be trusted
is reported as text, never sent as an image.
"""

import numpy as np
import pytest

from botting.screen import Frame
from maple.parsers import maple_parser
from maple.parsers.maple_parser import MapleParser


class _Pipe:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, item: object) -> None:
        self.sent.append(item)


class _Source:
    def __init__(self, frame: Frame) -> None:
        self.frame = frame

    def grab(self, handle: int) -> Frame:
        return self.frame


def _parser(monkeypatch: pytest.MonkeyPatch, frame: Frame) -> tuple[MapleParser, _Pipe]:
    monkeypatch.setattr(maple_parser, "frame_source", lambda: _Source(frame))
    pipe = _Pipe()
    parser = object.__new__(MapleParser)
    parser.pipe = pipe  # pyright: ignore[reportAttributeAccessIssue]
    return parser, pipe


def _frame(ok: bool, reason: str = "") -> Frame:
    pixels = np.zeros((4, 6, 3), dtype=np.uint8)
    return Frame(pixels, (6, 4), 0.0, True, ok, reason)


def test_a_good_frame_is_sent_as_its_pixels(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _frame(True)
    parser, pipe = _parser(monkeypatch, frame)

    parser._confirmation_with_image(1)  # pyright: ignore[reportPrivateUsage]

    assert pipe.sent == [frame.pixels]


def test_a_frame_that_is_not_ok_is_reported_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser, pipe = _parser(monkeypatch, _frame(False, "window not in front"))

    parser._confirmation_with_image(1)  # pyright: ignore[reportPrivateUsage]

    assert len(pipe.sent) == 1
    assert isinstance(pipe.sent[0], str)
    assert "window not in front" in pipe.sent[0]


KEYS = {"general": "1", "whisper": "h"}


@pytest.fixture(autouse=True)
def _keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(maple_parser, "_chat_keys", lambda ign: KEYS)


def test_write_whispers_a_player_when_given_to(monkeypatch: pytest.MonkeyPatch) -> None:
    parser, _ = _parser(monkeypatch, _frame(True))
    monkeypatch.setattr(maple_parser, "find_client", lambda: 7)

    request = parser.write("hello", "Alice", to="Bob")

    assert request.args == (7, "hello")
    assert request.kwargs == {
        "keys": KEYS,
        "channel": "whisper",
        "whisper_to": "Bob",
    }


def test_a_plain_write_names_no_channel_and_a_channel_write_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser, _ = _parser(monkeypatch, _frame(True))
    monkeypatch.setattr(maple_parser, "find_client", lambda: 7)

    assert parser.write("hi", "Alice").kwargs == {"keys": KEYS}
    assert parser.write("hi", "Alice", channel="party").kwargs == {
        "keys": KEYS,
        "channel": "party",
    }


def test_a_channel_or_whisper_write_still_carries_the_characters_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser, _ = _parser(monkeypatch, _frame(True))
    monkeypatch.setattr(maple_parser, "find_client", lambda: 7)
    asked: list[str] = []
    monkeypatch.setattr(
        maple_parser, "_chat_keys", lambda ign: asked.append(ign) or {"party": "9"}
    )

    for request in (
        parser.write("hi", "Alice", channel="party"),
        parser.write("hi", "Alice", to="Bob"),
    ):
        assert request.kwargs["keys"] == {"party": "9"}
    assert asked == ["Alice", "Alice"]
