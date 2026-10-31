"""Finding a game's window by what it is, not by what its title says."""

import ntpath

from . import _win32


class WindowNotFound(LookupError):
    """No visible top-level window matches the class and executable."""


class MultipleWindows(LookupError):
    """More than one visible top-level window matches the class and executable."""


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
