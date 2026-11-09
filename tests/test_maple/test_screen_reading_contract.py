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

import numpy as np
import pytest

import maple.screen
from botting.screen import Frame, Reading, Status
from maple.screen.buffs import BuffsReader
from maple.screen.chat import ChatReader
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MinimapReader
from maple.screen.minimap_title import MinimapTitleReader
from maple.screen.position import CameraReader
from maple.screen.quick_slots import SEARCH_EVERY, QuickSlotsReader
from maple.screen.sprites import GAUGE_LABEL
from maple.screen.status_bar import StatusBarReader
from tests.test_maple import test_screen_buffs as buffs
from tests.test_maple import test_screen_camera as camera
from tests.test_maple import test_screen_chat as chat
from tests.test_maple import test_screen_minimap as minimap
from tests.test_maple import test_screen_minimap_title as minimap_title
from tests.test_maple import test_screen_quick_slots as quick_slots
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


def _quick_slots(check: FrameCheck) -> Callable[[], Reading[Any]]:
    reader = QuickSlotsReader(quick_slots.sprites(), check)
    pixels = quick_slots.drawn_grid()

    def read() -> Reading[Any]:
        # The numbering is trusted once two searches agree.
        reader.read(quick_slots.frame(pixels, at=0.0))
        return reader.read(quick_slots.frame(pixels, at=SEARCH_EVERY))

    return read


def _chat(check: FrameCheck) -> Callable[[], Reading[Any]]:
    reader = ChatReader(chat.sprites(), check)
    frame = chat.chat_frame([chat.Row(text="Hi Hi!")])
    return lambda: reader.read(frame)


def _minimap_title(check: FrameCheck) -> Callable[[], Reading[Any]]:
    sprites = minimap_title.title_sprites()
    reader = MinimapTitleReader(
        sprites, MinimapReader(sprites, check), minimap_title.TITLES
    )
    frame = minimap_title.banner_frame()
    return lambda: reader.read(frame)


def _camera(check: FrameCheck) -> Callable[[], Reading[Any]]:
    render = camera.synthetic_render(1000, 800, 1)
    reader = CameraReader(camera.world_map(), frame_check=check, render=render)
    pixels = np.ascontiguousarray(render[100:700, 100:900, 2::-1])
    minimap.paste(pixels, minimap.SPRITES[GAUGE_LABEL], 10, 600 - 12)
    frame = minimap.frame(pixels)
    return lambda: reader.read(frame)


READERS = {
    StatusBarReader: _status_bar,
    MinimapReader: _minimap,
    BuffsReader: _buffs,
    QuickSlotsReader: _quick_slots,
    ChatReader: _chat,
    MinimapTitleReader: _minimap_title,
    CameraReader: _camera,
}

ASKS = {QuickSlotsReader: 2}
"""How often a reader asks the check in one `read()` of the factory above."""


def screen_readers() -> set[type]:
    """Every `*Reader` class `maple/screen/` and its packages define."""
    found: set[type] = set()
    for info in pkgutil.walk_packages(maple.screen.__path__, "maple.screen."):
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

    assert check.asked == ASKS.get(reader_class, 1)
    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert reading.detail == REJECTED


CHECK_SPRITES = {
    StatusBarReader: status_bar.SPRITES,
    MinimapReader: minimap.sprites(),
    BuffsReader: buffs.build_sprites(),
    QuickSlotsReader: quick_slots.sprites(),
    ChatReader: chat.sprites(),
    MinimapTitleReader: minimap_title.title_sprites(),
    CameraReader: minimap.sprites(),
}


@pytest.mark.parametrize("reader_class", READERS, ids=lambda cls: cls.__name__)
def test_the_same_frame_reads_when_the_check_passes(reader_class: type) -> None:
    """The control: the rejection above is the check's doing, not a frame that
    was never readable."""
    reading = READERS[reader_class](FrameCheck(CHECK_SPRITES[reader_class]))()

    assert reading.status is Status.READ, reading.detail
