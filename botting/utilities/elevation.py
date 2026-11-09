"""
Whether this process can send input to another one.

Windows blocks `SendInput` into a process of higher integrity (UIPI) and reports
nothing: the call succeeds and the key never arrives. `MapleStory.exe` is manifested
``requireAdministrator``, so a non-elevated sender is silently dropped. This module
compares the two tokens' elevation so a caller can refuse instead.
"""

import enum

import pywintypes
import win32api
import win32con
import win32process
import win32security


class Elevation(enum.Enum):
    ELEVATED = "elevated"
    NOT_ELEVATED = "not elevated"
    # The token could not be opened (access denied): the process has a higher
    # integrity than the caller, or has exited.
    UNREADABLE = "unreadable"


def _token_elevated(pid: int) -> bool | None:
    """
    Whether `pid`'s token is elevated, or None when the process or its token cannot
    be opened. The one place that calls the operating system, so tests stub it.
    """
    try:
        process = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
    except pywintypes.error:
        return None
    try:
        token = win32security.OpenProcessToken(process, win32con.TOKEN_QUERY)
    except pywintypes.error:
        return None
    finally:
        win32api.CloseHandle(process)
    try:
        return bool(
            win32security.GetTokenInformation(token, win32security.TokenElevation)
        )
    except pywintypes.error:
        return None
    finally:
        win32api.CloseHandle(token)


def process_elevation(pid: int) -> Elevation:
    elevated = _token_elevated(pid)
    if elevated is None:
        return Elevation.UNREADABLE
    return Elevation.ELEVATED if elevated else Elevation.NOT_ELEVATED


def window_process_id(handle: int) -> int:
    return win32process.GetWindowThreadProcessId(handle)[1]


def input_blocked_reason(pid: int, own_pid: int | None = None) -> str | None:
    """
    Why input from this process would not reach `pid`, or None when it would.

    Refused: the target is elevated and this process is not, or the target's token
    cannot be read (higher integrity than this process, or gone). An elevated caller
    can send to anything, and a non-elevated one to a non-elevated target.
    """
    own = process_elevation(
        win32api.GetCurrentProcessId() if own_pid is None else own_pid
    )
    target = process_elevation(pid)
    if target is Elevation.UNREADABLE:
        return (
            f"Process {pid} cannot be opened, which means it runs at a higher "
            "integrity than this one, so Windows would silently drop any input."
        )
    if target is Elevation.ELEVATED and own is not Elevation.ELEVATED:
        return (
            f"Process {pid} is elevated and this one is not, so Windows would "
            "silently drop any input."
        )
    return None
