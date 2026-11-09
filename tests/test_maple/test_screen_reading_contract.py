"""
The contract every screen reader keeps (`maple/screen/`): it asks the shared
frame check first, and a frame the check rejects gives `UNSURE` with no value,
however well the frame would otherwise read. "Never a wrong READ" starts here.

The frame is a good one on purpose: the only thing wrong with it is the check's
verdict, so a reader that skipped the check would read it and fail.
"""

import importlib
import inspect
import pkgutil
from collections.abc import Callable
from typing import Any

import pytest

import maple.screen
from botting.screen import Frame, Reading, Status
from maple.screen.buffs import BuffsReader
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MinimapReader
from maple.screen.status_bar import StatusBarReader
from tests.test_maple import test_screen_buffs as buffs
from tests.test_maple import test_screen_minimap as minimap
from tests.test_maple import test_screen_status_bar as status_bar

REJECTED = "frame rejected by the check"


class RejectingCheck(FrameCheck):
    """A frame check that rejects every frame, and counts how often it is asked."""

    def __init__(self) -> None:
        self.asked = 0

    def frame_usable[T](self, frame: Frame) -> Reading[T] | None:  # pyright: ignore[reportInvalidTypeVarUse]
        self.asked += 1
        return Reading.unsure(frame.captured_at, REJECTED)


def _status_bar(check: FrameCheck) -> Callable[[], Reading[Any]]:
    reader = StatusBarReader(status_bar.SPRITES, check)
    frame = status_bar.frame(status_bar.bar())
    return lambda: reader.read(frame)


def _minimap(check: FrameCheck) -> Callable[[], Reading[Any]]:
    reader = MinimapReader(minimap.sprites(), check)
    pixels = minimap.screen()
    minimap.draw_minimap(pixels, 250, 20, user_at=(37, 41))
    frame = minimap.frame(pixels)
    return lambda: reader.read(frame)


def _buffs(check: FrameCheck) -> Callable[[], Reading[Any]]:
    reader = BuffsReader(buffs.build_sprites(), check)
    frame = buffs.frame(buffs.screen("Haste"))
    return lambda: reader.read(frame, buffs.ASKED)


READERS = {
    StatusBarReader: _status_bar,
    MinimapReader: _minimap,
    BuffsReader: _buffs,
}


def screen_readers() -> set[type]:
    """Every `*Reader` class `maple/screen/` defines."""
    found: set[type] = set()
    for info in pkgutil.iter_modules(maple.screen.__path__, "maple.screen."):
        module = importlib.import_module(info.name)
        found |= {
            cls
            for name, cls in inspect.getmembers(module, inspect.isclass)
            if name.endswith("Reader") and cls.__module__ == module.__name__
        }
    return found


def test_every_screen_reader_is_under_the_contract() -> None:
    """A reader added to `maple/screen/` fails here until it joins `READERS`."""
    assert screen_readers() == set(READERS)


@pytest.mark.parametrize("reader_class", READERS, ids=lambda cls: cls.__name__)
def test_an_unusable_frame_is_unsure_with_no_value(reader_class: type) -> None:
    check = RejectingCheck()
    read = READERS[reader_class](check)

    reading = read()

    assert check.asked == 1
    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert reading.detail == REJECTED


CHECK_SPRITES = {
    StatusBarReader: status_bar.SPRITES,
    MinimapReader: minimap.sprites(),
    BuffsReader: buffs.build_sprites(),
}


@pytest.mark.parametrize("reader_class", READERS, ids=lambda cls: cls.__name__)
def test_the_same_frame_reads_when_the_check_passes(reader_class: type) -> None:
    """The control: the rejection above is the check's doing, not a frame that
    was never readable."""
    reading = READERS[reader_class](FrameCheck(CHECK_SPRITES[reader_class]))()

    assert reading.status is Status.READ, reading.detail
