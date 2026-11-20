"""
The Win32 calls `botting.screen` makes, one function each.

Kept apart so the tests can stub the operating system at one seam, and so
everything above this module deals in plain ints and tuples. Every
coordinate here is in physical pixels: `botting/__init__.py` declares
per-monitor DPI awareness (v2) before any of this runs.
"""

import ctypes
from collections.abc import Callable
from ctypes import wintypes

import pywintypes
import win32api
import win32con
import win32gui
import win32process

# Enough to read a process's image name, and grantable on an elevated process
# to an elevated caller (the bot runs elevated to send input to the client).
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# Enough to end a process and wait for it to be gone.
_PROCESS_TERMINATE = 0x0001
_SYNCHRONIZE = 0x00100000
_WAIT_OBJECT_0 = 0x00000000
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
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.TerminateProcess.restype = wintypes.BOOL
_kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_kernel32.WaitForSingleObject.restype = wintypes.DWORD

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


def is_window(hwnd: int) -> bool:
    """Whether `hwnd` is still a window."""
    return bool(win32gui.IsWindow(hwnd))


def terminate_window_process(hwnd: int, exit_code: int, timeout_ms: int) -> str | None:
    """
    End the process that owns `hwnd`, and wait up to `timeout_ms` for it to be
    gone. `None` when it ended, else why not.
    """
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    if not pid:
        return f"window {hwnd} has no owning process"
    process = _kernel32.OpenProcess(_PROCESS_TERMINATE | _SYNCHRONIZE, False, pid)
    if not process:
        return f"process {pid} can't be opened: error {ctypes.get_last_error()}"
    try:
        if not _kernel32.TerminateProcess(process, exit_code):
            return f"process {pid} can't be ended: error {ctypes.get_last_error()}"
        if _kernel32.WaitForSingleObject(process, timeout_ms) != _WAIT_OBJECT_0:
            return f"process {pid} was still running after {timeout_ms} ms"
        return None
    finally:
        _kernel32.CloseHandle(process)


def foreground_window() -> int:
    return win32gui.GetForegroundWindow()


def request_foreground(hwnd: int) -> list[str]:
    """
    Ask Windows to make `hwnd` the foreground window, sending no key and no click:
    restore it if it is minimised, borrow the current foreground window's input
    queue (`AttachThreadInput`: in practice it lets this thread past the
    foreground lock, though Microsoft documents no such effect), raise it
    (`BringWindowToTop`), then `SetForegroundWindow`.

    Each call is tried even when an earlier one is refused: a refused attach or
    z-order change must not stop `SetForegroundWindow`, the call that matters.

    :return: Every call Windows refused, as ``"<function> (<reason>)"``, in the order
        tried; empty when they all went through. Whether the window really is in
        front is for the caller to check (`foreground_window`): Windows may accept
        every call and still leave it behind.
    """
    refused: list[str] = []

    def attempt(call: Callable[[], object]) -> bool:
        try:
            call()
        except Win32Error as err:
            refused.append(_refusal(err))
            return False
        return True

    if win32gui.IsIconic(hwnd):
        attempt(lambda: win32gui.ShowWindow(hwnd, win32con.SW_RESTORE))
    current = win32gui.GetForegroundWindow()
    mine = win32api.GetCurrentThreadId()
    try:
        theirs = win32process.GetWindowThreadProcessId(current)[0] if current else mine
    except Win32Error as err:  # the foreground window closed meanwhile
        refused.append(_refusal(err))
        theirs = mine
    attached = theirs != mine and attempt(
        lambda: win32process.AttachThreadInput(mine, theirs, True)
    )
    try:
        attempt(lambda: win32gui.BringWindowToTop(hwnd))
        attempt(lambda: win32gui.SetForegroundWindow(hwnd))
    finally:
        if attached:
            attempt(lambda: win32process.AttachThreadInput(mine, theirs, False))
    return refused


def _refusal(err: Win32Error) -> str:
    # `SetForegroundWindow` refused by the foreground lock fails with no error code.
    reason = err.strerror.rstrip(".") if err.winerror else "no error code"
    return f"{err.funcname} ({reason})"


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
