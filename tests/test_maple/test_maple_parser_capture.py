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
