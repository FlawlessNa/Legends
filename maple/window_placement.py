"""
Where the game client's window is on the screen, and where a window of ours can
go beside it: the helpers `maple.probe` and the Hunting Area window share.

They read the desktop's geometry and move nothing; sending a key or a mouse event
is not done here.
"""

import win32api
import win32con
import win32gui

from botting.utilities import Box


def client_size(handle: int) -> tuple[int, int]:
    """The client area's width and height."""
    _left, _top, right, bottom = win32gui.GetClientRect(handle)
    return right, bottom


def client_rect(handle: int) -> Box:
    """The client area on the screen, as `FrameSource` reads it."""
    width, height = client_size(handle)
    left, top = win32gui.ClientToScreen(handle, (0, 0))
    return Box(left=left, top=top, right=left + width, bottom=top + height)


def work_area() -> Box:
    """The primary monitor less the taskbar."""
    primary = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    left, top, right, bottom = win32api.GetMonitorInfo(primary)["Work"]
    return Box(left=left, top=top, right=right, bottom=bottom)


def screen_size() -> tuple[int, int]:
    """The primary monitor's width and height."""
    return (
        win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
        win32api.GetSystemMetrics(win32con.SM_CYSCREEN),
    )


def on_screen(rect: Box, screen: tuple[int, int]) -> bool:
    """Whether `rect` is entirely on a screen of that size."""
    return (
        rect.left >= 0
        and rect.top >= 0
        and rect.right <= screen[0]
        and rect.bottom <= screen[1]
    )


def fitted_origin(
    rect: Box, screen: tuple[int, int], work_area: Box
) -> tuple[int, int] | None:
    """
    Where to put the client area's top-left so it is entirely on the primary
    monitor, moving it as little as possible: inside the work area when it fits
    there, else inside the screen. `None` when it is already on the screen, or
    is bigger than the screen and can't be.
    """
    if on_screen(rect, screen):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width > screen[0] or height > screen[1]:
        return None
    bounds = work_area
    if width > work_area.right - work_area.left or (
        height > work_area.bottom - work_area.top
    ):
        bounds = Box(left=0, top=0, right=screen[0], bottom=screen[1])
    left = min(max(rect.left, bounds.left), bounds.right - width)
    top = min(max(rect.top, bounds.top), bounds.bottom - height)
    return left, top
