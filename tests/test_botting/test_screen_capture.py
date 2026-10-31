"""`FrameSource.grab`: the client area's pixels, and whether they are the client's."""

import dataclasses
from collections.abc import Iterator

import numpy as np
import pytest
from numpy.typing import NDArray

from botting.screen import Frame, FrameSource
from botting.screen import _win32 as win32
from botting.screen._win32 import Rect

HANDLE = 0x1234
OTHER = 0x9999
RECT: Rect = (100, 50, 900, 650)  # an 800x600 client area at (100, 50)
SCREEN = (1920, 1080)


class _FakeCamera:
    def __init__(self, frames: list[NDArray[np.uint8] | Exception | None]) -> None:
        self.frames = list(frames)
        self.regions: list[Rect] = []
        self.released = False

    def grab(self, region: Rect) -> NDArray[np.uint8] | None:
        self.regions.append(region)
        frame = self.frames.pop(0)
        if isinstance(frame, Exception):
            raise frame
        return frame

    def release(self) -> None:
        self.released = True


class _World:
    """What the stubbed Win32 answers, one value per call, in call order."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.foreground: Iterator[int] = iter(())
        self.rects: Iterator[Rect] = iter(())
        monkeypatch.setattr(win32, "foreground_window", lambda: next(self.foreground))
        monkeypatch.setattr(
            win32, "client_rect_on_screen", lambda hwnd: next(self.rects)
        )
        monkeypatch.setattr(win32, "primary_screen_size", lambda: SCREEN)

    def set(self, foreground: list[int], rects: list[Rect]) -> None:
        self.foreground = iter(foreground)
        self.rects = iter(rects)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> _World:
    return _World(monkeypatch)


def _pixels(value: int = 7) -> NDArray[np.uint8]:
    return np.full((600, 800, 3), value, np.uint8)


def _source(camera: _FakeCamera) -> FrameSource:
    return FrameSource(camera_factory=lambda: camera)


# ── a trusted copy ──────────────────────────────────────────────────────────


def test_copies_the_client_rectangle_at_its_screen_origin(world: _World) -> None:
    camera = _FakeCamera([_pixels()])
    world.set([HANDLE, HANDLE], [RECT, RECT])

    frame = _source(camera).grab(HANDLE)

    assert camera.regions == [RECT]
    assert frame.ok
    assert frame.reason == ""
    assert frame.fresh
    assert frame.client_size == (800, 600)
    assert frame.pixels.shape == (600, 800, 3)
    assert frame.pixels.dtype == np.uint8


def test_frame_is_frozen(world: _World) -> None:
    world.set([HANDLE, HANDLE], [RECT, RECT])
    frame = _source(_FakeCamera([_pixels()])).grab(HANDLE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        frame.ok = False  # pyright: ignore[reportAttributeAccessIssue] - the point


# ── a copy that isn't the client's own pixels ───────────────────────────────


def test_not_ok_when_another_window_is_in_front_before_the_copy(
    world: _World,
) -> None:
    world.set([OTHER, HANDLE], [RECT, RECT])
    frame = _source(_FakeCamera([_pixels()])).grab(HANDLE)
    assert not frame.ok
    assert "before" in frame.reason


def test_not_ok_when_another_window_comes_in_front_during_the_copy(
    world: _World,
) -> None:
    world.set([HANDLE, OTHER], [RECT, RECT])
    frame = _source(_FakeCamera([_pixels()])).grab(HANDLE)
    assert not frame.ok
    assert "after" in frame.reason


def test_not_ok_when_the_client_rectangle_changes_during_the_copy(
    world: _World,
) -> None:
    resized: Rect = (100, 50, 1124, 818)
    world.set([HANDLE, HANDLE], [RECT, resized])
    frame = _source(_FakeCamera([_pixels()])).grab(HANDLE)
    assert not frame.ok
    assert "changed" in frame.reason


def test_not_ok_and_nothing_copied_when_the_client_is_off_the_monitor(
    world: _World,
) -> None:
    camera = _FakeCamera([])
    world.set([HANDLE], [(1500, 50, 2300, 650)])
    frame = _source(camera).grab(HANDLE)
    assert not frame.ok
    assert camera.regions == []


def test_not_ok_when_the_client_area_is_empty(world: _World) -> None:
    camera = _FakeCamera([])
    world.set([HANDLE], [(100, 50, 100, 50)])
    frame = _source(camera).grab(HANDLE)
    assert not frame.ok
    assert camera.regions == []


# ── no new frame ────────────────────────────────────────────────────────────


def test_no_new_frame_returns_the_previous_one_not_fresh(world: _World) -> None:
    first = _pixels(1)
    source = _source(_FakeCamera([first, None]))
    world.set([HANDLE, HANDLE, HANDLE, HANDLE], [RECT, RECT, RECT, RECT])

    fresh = source.grab(HANDLE)
    repeat = source.grab(HANDLE)

    assert fresh.fresh
    assert not repeat.fresh
    assert repeat.ok
    assert repeat.pixels is first
    assert repeat.captured_at == fresh.captured_at


def test_a_repeated_frame_is_still_checked(world: _World) -> None:
    source = _source(_FakeCamera([_pixels(), None]))
    world.set([HANDLE, HANDLE, OTHER, OTHER], [RECT, RECT, RECT, RECT])

    source.grab(HANDLE)
    repeat = source.grab(HANDLE)

    assert not repeat.fresh
    assert not repeat.ok


def test_no_new_frame_and_none_before_is_not_ok(world: _World) -> None:
    world.set([HANDLE, HANDLE], [RECT, RECT])
    frame = _source(_FakeCamera([None])).grab(HANDLE)
    assert not frame.ok
    assert not frame.fresh
    assert frame.client_size == (800, 600)


def test_previous_frame_of_another_rectangle_is_not_reused(world: _World) -> None:
    moved: Rect = (200, 50, 1000, 650)
    source = _source(_FakeCamera([_pixels(), None]))
    world.set([HANDLE, HANDLE, HANDLE, HANDLE], [RECT, RECT, moved, moved])

    source.grab(HANDLE)
    frame = source.grab(HANDLE)

    assert not frame.ok


# ── capture failures ────────────────────────────────────────────────────────


def test_a_capture_failure_is_not_ok_and_the_camera_is_recreated(
    world: _World,
) -> None:
    broken = _FakeCamera([OSError("access lost")])
    working = _FakeCamera([_pixels()])
    cameras = iter([broken, working])
    source = FrameSource(camera_factory=lambda: next(cameras))
    world.set([HANDLE, HANDLE, HANDLE, HANDLE], [RECT, RECT, RECT, RECT])

    failed = source.grab(HANDLE)
    recovered = source.grab(HANDLE)

    assert not failed.ok
    assert "access lost" in failed.reason
    assert broken.released
    assert recovered.ok


def test_a_window_that_closed_is_not_ok(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _closed(hwnd: int) -> Rect:
        raise win32.Win32Error(1400, "GetClientRect", "Invalid window handle.")

    monkeypatch.setattr(win32, "client_rect_on_screen", _closed)
    world.foreground = iter([HANDLE])
    frame: Frame = _source(_FakeCamera([])).grab(HANDLE)
    assert not frame.ok
    assert "Invalid window handle" in frame.reason
