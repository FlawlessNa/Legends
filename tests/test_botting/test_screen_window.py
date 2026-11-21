"""`find_window`: the one visible window of a class, owned by a named executable."""

from dataclasses import dataclass

import pytest

from botting.screen import (
    MultipleWindows,
    WindowNotFound,
    bring_to_front,
    find_window,
    window,
)
from botting.screen import _win32 as win32
from botting.utilities.elevation import Elevation

CLASS = "MapleStoryClass"
EXE = "MapleStory.exe"


@dataclass
class _Window:
    hwnd: int
    class_name: str
    image: str | None
    visible: bool = True


@pytest.fixture
def desktop(monkeypatch: pytest.MonkeyPatch) -> list[_Window]:
    """The windows the stubbed Win32 enumerates; a test appends to it."""
    windows: list[_Window] = []
    by_handle = lambda hwnd: next(w for w in windows if w.hwnd == hwnd)  # noqa: E731
    monkeypatch.setattr(win32, "top_level_windows", lambda: [w.hwnd for w in windows])
    monkeypatch.setattr(win32, "is_visible", lambda hwnd: by_handle(hwnd).visible)
    monkeypatch.setattr(win32, "class_name", lambda hwnd: by_handle(hwnd).class_name)
    monkeypatch.setattr(win32, "process_image_path", lambda hwnd: by_handle(hwnd).image)
    return windows


def test_returns_the_window_of_that_class_and_executable(
    desktop: list[_Window],
) -> None:
    desktop += [
        _Window(1, "CabinetWClass", r"C:\Windows\explorer.exe"),  # titled MapleStory
        _Window(2, CLASS, r"D:\Games\MSCW\MapleStory.exe"),
    ]
    assert find_window(CLASS, EXE) == 2


def test_executable_is_compared_by_file_name_case_insensitively(
    desktop: list[_Window],
) -> None:
    desktop.append(_Window(7, CLASS, r"D:\GAMES\MSCW\MAPLESTORY.EXE"))
    assert find_window(CLASS, "maplestory.exe") == 7


def test_ignores_same_class_from_another_executable(desktop: list[_Window]) -> None:
    desktop += [
        _Window(3, CLASS, r"C:\Tools\NotTheGame.exe"),
        _Window(4, CLASS, r"C:\Tools\MapleStory.exe.bak"),
        _Window(5, CLASS, None),  # process couldn't be opened
    ]
    with pytest.raises(WindowNotFound) as excinfo:
        find_window(CLASS, EXE)
    assert CLASS in str(excinfo.value)
    assert EXE in str(excinfo.value)


def test_ignores_invisible_windows(desktop: list[_Window]) -> None:
    desktop += [
        _Window(8, CLASS, r"D:\MSCW\MapleStory.exe", visible=False),
        _Window(9, CLASS, r"D:\MSCW\MapleStory.exe"),
    ]
    assert find_window(CLASS, EXE) == 9


def test_raises_when_nothing_matches(desktop: list[_Window]) -> None:
    with pytest.raises(WindowNotFound) as excinfo:
        find_window(CLASS, EXE)
    assert CLASS in str(excinfo.value)
    assert EXE in str(excinfo.value)


def test_raises_when_more_than_one_matches(desktop: list[_Window]) -> None:
    desktop += [
        _Window(10, CLASS, r"D:\MSCW\MapleStory.exe"),
        _Window(11, CLASS, r"E:\Other\maplestory.exe"),
    ]
    with pytest.raises(MultipleWindows) as excinfo:
        find_window(CLASS, EXE)
    message = str(excinfo.value)
    assert CLASS in message
    assert EXE in message
    assert "10" in message
    assert "11" in message


# --- bring_to_front ---------------------------------------------------------

FRONT_IMAGES = {
    3: r"C:\Program Files\Browser\browser.exe",
    4: r"C:\Windows\SystemApps\Microsoft.LockApp_cw5n1h2txyewy\LockApp.exe",
}


def _foreground(
    monkeypatch: pytest.MonkeyPatch,
    current: int,
    grants: bool,
    refused: list[str] | None = None,
    me: Elevation = Elevation.ELEVATED,
    target: Elevation = Elevation.ELEVATED,
) -> list[int]:
    """
    Stubs the foreground; `request_foreground` moves it to the target if `grants`,
    and reports `refused`. `me` and `target` are this process's and the target
    window's elevation.
    """
    state = {"front": current}
    asked: list[int] = []
    monkeypatch.setattr(win32, "foreground_window", lambda: state["front"])
    monkeypatch.setattr(win32, "is_window", lambda hwnd: True)
    monkeypatch.setattr(win32, "process_image_path", FRONT_IMAGES.get)
    monkeypatch.setattr(window, "window_process_id", lambda hwnd: 1000 + hwnd)
    monkeypatch.setattr(window.os, "getpid", lambda: 1)
    monkeypatch.setattr(
        window, "process_elevation", lambda pid: me if pid == 1 else target
    )

    def request(hwnd: int) -> list[str]:
        asked.append(hwnd)
        if grants:
            state["front"] = hwnd
        return list(refused or [])

    monkeypatch.setattr(win32, "request_foreground", request)
    return asked


def test_a_window_already_in_front_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _foreground(monkeypatch, current=7, grants=True)

    assert bring_to_front(7) is None
    assert asked == []


def test_a_window_behind_another_is_brought_to_the_front(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _foreground(monkeypatch, current=3, grants=True)

    assert bring_to_front(7) is None
    assert asked == [7]


def test_a_refused_call_does_not_matter_when_the_window_came_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch, current=3, grants=True, refused=["BringWindowToTop (denied)"]
    )

    assert bring_to_front(7) is None


def test_a_window_windows_will_not_bring_forward_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(monkeypatch, current=3, grants=False)

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "accepted every call but left window 7 behind" in reason
    assert "(in front: browser.exe)" in reason
    assert "by hand" in reason


def test_a_non_elevated_caller_is_told_to_run_the_terminal_as_administrator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch,
        current=3,
        grants=False,
        refused=[
            "BringWindowToTop (Access is denied)",
            "SetForegroundWindow (no error code)",
        ],
        me=Elevation.NOT_ELEVATED,
    )

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert (
        "Windows refused BringWindowToTop (Access is denied), "
        "SetForegroundWindow (no error code) (in front: browser.exe)."
    ) in reason
    assert "elevated process and this one is not" in reason
    assert "Run this terminal as administrator" in reason


def test_a_target_whose_token_cannot_be_read_counts_as_elevated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch,
        current=3,
        grants=False,
        me=Elevation.NOT_ELEVATED,
        target=Elevation.UNREADABLE,
    )

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "Run this terminal as administrator" in reason


def test_a_non_elevated_caller_and_target_is_not_told_about_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch,
        current=3,
        grants=False,
        me=Elevation.NOT_ELEVATED,
        target=Elevation.NOT_ELEVATED,
    )

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "administrator" not in reason


def test_a_refused_attach_says_the_foreground_lock_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch,
        current=3,
        grants=False,
        refused=["AttachThreadInput (Access is denied)"],
    )

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "Windows refused AttachThreadInput (Access is denied)" in reason
    assert "input queue of browser.exe" in reason
    assert "foreground lock" in reason
    assert "by hand" in reason
    assert "administrator" not in reason


def test_the_lock_screen_in_front_says_the_session_is_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(
        monkeypatch,
        current=4,
        grants=False,
        refused=["AttachThreadInput (Access is denied)"],
        me=Elevation.NOT_ELEVATED,
    )

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "(in front: LockApp.exe)" in reason
    assert "The session is locked" in reason
    assert "Unlock the session" in reason
    assert "administrator" not in reason


def test_a_front_window_of_unknown_process_is_still_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _foreground(monkeypatch, current=9, grants=False)

    reason = bring_to_front(7, timeout=0.0)

    assert reason is not None
    assert "(in front: window 9, process unknown)" in reason


def test_a_gone_window_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = _foreground(monkeypatch, current=3, grants=True)
    monkeypatch.setattr(win32, "is_window", lambda hwnd: False)

    assert bring_to_front(7) == "Window 7 is gone."
    assert asked == []
