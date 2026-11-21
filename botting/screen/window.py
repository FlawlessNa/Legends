"""
Finding a game's window by what it is, not by what its title says, bringing it
to the front, and closing the game it belongs to.
"""

import ntpath
import os
import time

from botting.utilities.elevation import Elevation, process_elevation, window_process_id

from . import _win32


class WindowNotFound(LookupError):
    """No visible top-level window matches the class and executable."""


class MultipleWindows(LookupError):
    """More than one visible top-level window matches the class and executable."""


class ClientNotClosed(RuntimeError):
    """`close_client` couldn't end the window's process, or its window stayed."""


#: How long `close_client` waits for the process to end, then for its window to go.
CLOSE_TIMEOUT = 5.0
#: How long `bring_to_front` waits for the window to be in front.
FRONT_TIMEOUT = 1.0
#: The exit code the closed process is given.
CLOSED_EXIT_CODE = 1
#: The Windows lock screen's executable, cased as `casefold` gives it: it is in
#: front only while the session is locked.
LOCK_SCREEN = "lockapp.exe"


def find_window(class_name: str, executable: str) -> int:
    """
    The one visible top-level window of class `class_name` whose process image
    is `executable`, compared by file name and case-insensitively
    (`"MapleStory.exe"` matches `D:\\Games\\...\\maplestory.EXE`).

    Neither the title nor the window's contents are read, so an Explorer window
    titled like the game, or a second program reusing its class name, is ignored.

    :raises WindowNotFound: when no window matches.
    :raises MultipleWindows: when more than one does.
    """
    wanted = executable.casefold()
    matches: list[int] = []
    for hwnd in _win32.top_level_windows():
        if not _win32.is_visible(hwnd) or _win32.class_name(hwnd) != class_name:
            continue
        image = _win32.process_image_path(hwnd)
        if image is not None and ntpath.basename(image).casefold() == wanted:
            matches.append(hwnd)

    if not matches:
        raise WindowNotFound(
            f"No visible window of class {class_name!r} belongs to a process "
            f"named {executable!r}. Is the client running?"
        )
    if len(matches) > 1:
        raise MultipleWindows(
            f"{len(matches)} visible windows of class {class_name!r} belong to "
            f"processes named {executable!r} (handles {matches}); "
            "expected exactly one."
        )
    return matches[0]


def bring_to_front(handle: int, timeout: float = FRONT_TIMEOUT) -> str | None:
    """
    Bring the window `handle` to the front, and wait up to `timeout` seconds for
    it to be there. It sends no key and no click: it only asks Windows to change
    the foreground window (`_win32.request_foreground`).

    :return: `None` when the window is in front, else why it is not and what to
        do about it, in full sentences: which calls Windows refused, which
        program is in front, and whether elevation, a locked session or the
        foreground lock is in the way.
    """
    in_front = _win32.foreground_window()
    if in_front == handle:
        return None
    if not _win32.is_window(handle):
        return f"Window {handle} is gone."
    refused = _win32.request_foreground(handle)
    deadline = time.monotonic() + timeout
    while _win32.foreground_window() != handle:
        if time.monotonic() >= deadline:
            return _why_not_in_front(handle, in_front, refused)
        time.sleep(0.02)
    return None


def _why_not_in_front(handle: int, in_front: int, refused: list[str]) -> str:
    """
    What `bring_to_front` reports when the window stayed behind `in_front`, the
    window that was in front when it asked: what Windows said, then the most
    specific reason it knows of, with what to do.
    """
    front_name = _image_name(in_front)
    if refused:
        said = f"Windows refused {', '.join(refused)}"
    else:
        said = f"Windows accepted every call but left window {handle} behind"
    said += f" (in front: {front_name})."
    if front_name.casefold() == LOCK_SCREEN:
        advice = (
            "The session is locked: the lock screen is in front, and no program "
            "can bring a window over it. Unlock the session, then try again."
        )
    elif _elevation_blocks(handle):
        advice = (
            f"Window {handle} belongs to an elevated process and this one is not, "
            "and Windows does not let a process bring a window of higher integrity "
            "forward (UIPI). Run this terminal as administrator, then try again."
        )
    elif any(call.startswith("AttachThreadInput ") for call in refused):
        advice = (
            f"Windows would not let this process share the input queue of "
            f"{front_name}, so the foreground lock held; getting past it would "
            "take a key or a click, which this does not send. Bring the window to "
            "the front by hand, then try again."
        )
    else:
        advice = (
            "Windows may refuse a foreground change even when it allows the calls; "
            "getting past it would take a key or a click, which this does not "
            "send. Bring the window to the front by hand, then try again."
        )
    return f"{said} {advice}"


def _image_name(hwnd: int) -> str:
    """The file name of the executable that owns `hwnd`, for a message."""
    if not hwnd:
        return "no window"
    image = _win32.process_image_path(hwnd)
    return ntpath.basename(image) if image else f"window {hwnd}, process unknown"


def _elevation_blocks(handle: int) -> bool:
    """
    Whether this process is not elevated and `handle`'s process is, or runs at an
    integrity this process can't even read (its token can't be opened).
    """
    if process_elevation(os.getpid()) is Elevation.ELEVATED:
        return False
    return process_elevation(window_process_id(handle)) is not Elevation.NOT_ELEVATED


def close_client(handle: int, timeout: float = CLOSE_TIMEOUT) -> None:
    """
    Close the game that owns the window `handle`: end its process, then confirm
    the window is gone.

    The process is terminated rather than asked to close (`WM_CLOSE`), which a
    game may answer with a confirmation that someone would then have to click.
    A window that is already gone is closed already. A process that can't be
    ended is no failure if its window goes all the same: it was already ending,
    and its window outlives it for a moment.

    :param handle: The game's window, as `find_window` found it.
    :param timeout: Seconds to wait for the process to end, then as long again
        for its window to be gone.
    :raises ClientNotClosed: when the window is still there after `timeout`,
        naming why the process couldn't be ended if it couldn't.
    """
    if not _win32.is_window(handle):
        return
    problem = _win32.terminate_window_process(
        handle, CLOSED_EXIT_CODE, int(timeout * 1000)
    )
    deadline = time.monotonic() + timeout
    while _win32.is_window(handle):
        if time.monotonic() > deadline:
            if problem is not None:
                raise ClientNotClosed(
                    f"Could not close the client of window {handle}: {problem}"
                )
            raise ClientNotClosed(
                f"Window {handle} was still there {timeout} s after its process ended."
            )
        time.sleep(0.05)
