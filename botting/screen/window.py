"""
Finding a game's window by what it is, not by what its title says, and closing
the game it belongs to.
"""

import ntpath
import time

from . import _win32


class WindowNotFound(LookupError):
    """No visible top-level window matches the class and executable."""


class MultipleWindows(LookupError):
    """More than one visible top-level window matches the class and executable."""


class ClientNotClosed(RuntimeError):
    """`close_client` couldn't end the window's process, or its window stayed."""


#: How long `close_client` waits for the process to end, then for its window to go.
CLOSE_TIMEOUT = 5.0
#: The exit code the closed process is given.
CLOSED_EXIT_CODE = 1


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
