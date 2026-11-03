"""
The Win32 calls `botting.screen` makes, one function each.

Kept apart so the tests can stub the operating system at one seam, and so
everything above this module deals in plain ints and tuples. Every
coordinate here is in physical pixels: `botting/__init__.py` declares
per-monitor DPI awareness (v2) before any of this runs.
"""

import ctypes
from ctypes import wintypes

import pywintypes
import win32api
import win32con
import win32gui
import win32process

# Enough to read a process's image name, and grantable on an elevated process
# to an elevated caller (the bot runs elevated to send input to the client).
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_MAX_PATH_CHARS = 32768

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL

Rect = tuple[int, int, int, int]  # left, top, right, bottom

# What pywin32 raises when a call fails, for instance on a handle that closed.
Win32Error = pywintypes.error


def top_level_windows() -> list[int]:
    """Every top-level window, in Z order."""
    handles: list[int] = []

    def _collect(hwnd: int, _: None) -> bool:
        handles.append(hwnd)
        return True

    win32gui.EnumWindows(_collect, None)
    return handles


def is_visible(hwnd: int) -> bool:
    return bool(win32gui.IsWindowVisible(hwnd))


def class_name(hwnd: int) -> str:
    return win32gui.GetClassName(hwnd) or ""


def process_image_path(hwnd: int) -> str | None:
    """
    The full path of the executable that owns `hwnd`, or None when the process
    can't be opened (it exited, or it is protected from this caller).
    """
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    process = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return None
    try:
        size = wintypes.DWORD(_MAX_PATH_CHARS)
        buffer = ctypes.create_unicode_buffer(_MAX_PATH_CHARS)
        if not _kernel32.QueryFullProcessImageNameW(
            process, 0, buffer, ctypes.byref(size)
        ):
            return None
        return buffer.value
    finally:
        _kernel32.CloseHandle(process)


def foreground_window() -> int:
    return win32gui.GetForegroundWindow()


def client_rect_on_screen(hwnd: int) -> Rect:
    """
    The window's client area in screen coordinates: `GetClientRect` gives its
    size, `ClientToScreen` places its origin. No border or title bar height
    is assumed.
    """
    _, _, width, height = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return left, top, left + width, top + height


def primary_screen_size() -> tuple[int, int]:
    """The primary monitor's size, read now rather than once at import."""
    return (
        win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
        win32api.GetSystemMetrics(win32con.SM_CYSCREEN),
    )
