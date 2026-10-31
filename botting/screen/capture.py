"""
Capturing a window's client area with Desktop Duplication.

`FrameSource.grab(handle)` copies the client area out of the desktop image, at
its real origin, in physical pixels, and says whether the copy can be trusted
to be that window's own pixels. Desktop Duplication copies what is on the
screen, so a window in front of the client, a UAC prompt or the lock screen
would be copied as if it were the client: `Frame.ok` is what tells them apart.
"""

import logging
import time
from _ctypes import COMError  # what comtypes, under dxcam, raises on a DXGI failure
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from . import _win32
from ._win32 import Rect

logger = logging.getLogger(__name__)


@dataclass(frozen=True, eq=False)
class Frame:
    """
    One copy of a window's client area.

    :param pixels: `H x W x 3` BGR `uint8`.
    :param client_size: `(width, height)` of the client area when it was copied.
    :param captured_at: `time.monotonic()` when the pixels were copied. A frame
        that isn't `fresh` keeps the time of the copy it repeats.
    :param fresh: False when the screen hadn't changed since the last copy, and
        this frame repeats the previous one.
    :param ok: True only when the window was in front before and after the copy,
        and its client rectangle didn't move or resize in between.
    :param reason: why `ok` is False; empty when it is True.
    """

    pixels: NDArray[np.uint8]
    client_size: tuple[int, int]
    captured_at: float
    fresh: bool
    ok: bool
    reason: str = ""


class Camera(Protocol):
    """The part of `dxcam.DXCamera` that `FrameSource` uses."""

    def grab(self, region: Rect) -> NDArray[np.uint8] | None: ...

    def release(self) -> None: ...


def _create_dxcam() -> Camera:
    import dxcam  # only a process that captures pays for DXGI's start-up

    return dxcam.create(output_color="BGR")


class FrameSource:
    """
    Desktop Duplication of the primary monitor, created once per process: use
    `frame_source()` rather than building one.

    The camera itself is created on the first `grab`, and again after a capture
    failure (a display-mode change, the lock screen), so a source survives them.
    """

    def __init__(self, camera_factory: Callable[[], Camera] = _create_dxcam) -> None:
        self._camera_factory = camera_factory
        self._camera: Camera | None = None
        self._last: tuple[int, Rect, Frame] | None = None

    def grab(self, handle: int) -> Frame:
        """
        The client area of `handle`, read from `GetClientRect` and
        `ClientToScreen`. Never raises because of what is on screen: a copy that
        can't be trusted comes back with `ok=False` and a reason.
        """
        try:
            foreground_before = _win32.foreground_window()
            rect = _win32.client_rect_on_screen(handle)
        except _win32.Win32Error as exc:
            return _blank((0, 0), f"window {handle} can't be read: {exc}")

        size = (rect[2] - rect[0], rect[3] - rect[1])
        if size[0] <= 0 or size[1] <= 0:
            return _blank((0, 0), f"window {handle} has no client area (minimised?)")
        screen_w, screen_h = _win32.primary_screen_size()
        if rect[0] < 0 or rect[1] < 0 or rect[2] > screen_w or rect[3] > screen_h:
            return _blank(
                size,
                f"client rectangle {rect} isn't entirely on the primary monitor "
                f"({screen_w}x{screen_h})",
            )

        pixels, failure = self._copy(rect)

        try:
            foreground_after = _win32.foreground_window()
            rect_after = _win32.client_rect_on_screen(handle)
        except _win32.Win32Error as exc:
            return _blank(size, f"window {handle} can't be read: {exc}")

        reason = _distrust(
            handle, foreground_before, foreground_after, rect, rect_after
        )
        if failure:
            return _blank(size, failure)

        if pixels is not None:
            frame = Frame(
                pixels=pixels,
                client_size=size,
                captured_at=time.monotonic(),
                fresh=True,
                ok=not reason,
                reason=reason,
            )
            self._last = (handle, rect, frame)
            return frame

        # Nothing changed on screen since the last copy, so the last copy of
        # this same rectangle is still what the screen shows.
        if self._last is not None and self._last[:2] == (handle, rect):
            return replace(self._last[2], fresh=False, ok=not reason, reason=reason)
        return _blank(
            size, reason or "no frame of this client rectangle has been copied yet"
        )

    def _copy(self, rect: Rect) -> tuple[NDArray[np.uint8] | None, str]:
        """The pixels (None when the screen hasn't changed), or why the copy failed."""
        try:
            if self._camera is None:
                self._camera = self._camera_factory()
            return self._camera.grab(region=rect), ""
        except (COMError, OSError, RuntimeError, ValueError) as exc:
            logger.warning("Desktop Duplication failed, recreating it: %r", exc)
            self._reset()
            return None, f"Desktop Duplication failed: {exc!r}"

    def _reset(self) -> None:
        camera, self._camera, self._last = self._camera, None, None
        if camera is not None:
            try:
                camera.release()
            except (COMError, OSError, RuntimeError) as exc:
                logger.debug("Releasing the failed camera raised %r.", exc)


def _distrust(
    handle: int, fg_before: int, fg_after: int, rect: Rect, rect_after: Rect
) -> str:
    """Why the copy isn't `handle`'s own pixels, or `""` when nothing says so."""
    if fg_before != handle:
        return f"window {handle} wasn't in front before the copy ({fg_before} was)"
    if fg_after != handle:
        return f"window {handle} wasn't in front after the copy ({fg_after} was)"
    if rect_after != rect:
        return f"client rectangle changed during the copy: {rect} -> {rect_after}"
    return ""


def _blank(size: tuple[int, int], reason: str) -> Frame:
    width, height = size
    return Frame(
        pixels=np.zeros((height, width, 3), np.uint8),
        client_size=size,
        captured_at=time.monotonic(),
        fresh=False,
        ok=False,
        reason=reason,
    )


_source: FrameSource | None = None


def frame_source() -> FrameSource:
    """This process's `FrameSource`, created on first use."""
    global _source  # one Desktop Duplication per process, by design
    if _source is None:
        _source = FrameSource()
    return _source
