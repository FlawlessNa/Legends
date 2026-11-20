"""
`_win32.request_foreground` against fake `win32gui`, `win32process` and `win32api`
modules: each call is tried even when an earlier one is refused, every refusal is
reported, and nothing but those calls is made (no key, no click: the fakes have
no other attribute, so any other call would raise).
"""

from dataclasses import dataclass, field

import pytest

from botting.screen import _win32 as win32

TARGET = 70
OTHER_WINDOW = 30
MY_THREAD = 1
THEIR_THREAD = 2
ACCESS_DENIED = 5


def _denied(funcname: str) -> win32.Win32Error:
    return win32.Win32Error(ACCESS_DENIED, funcname, "Access is denied.")


@dataclass
class _Windows:
    """The fake operating system: what is in front, and which calls it refuses."""

    foreground: int = OTHER_WINDOW
    iconic: bool = False
    refuse: dict[str, win32.Win32Error] = field(default_factory=dict)
    calls: list[tuple[object, ...]] = field(default_factory=list)

    def _call(self, name: str, *args: object) -> None:
        self.calls.append((name, *args))
        if name in self.refuse:
            raise self.refuse[name]


class _Gui:
    def __init__(self, windows: _Windows) -> None:
        self._w = windows

    def IsIconic(self, hwnd: int) -> bool:
        return self._w.iconic

    def ShowWindow(self, hwnd: int, command: int) -> None:
        self._w._call("ShowWindow", hwnd, command)

    def GetForegroundWindow(self) -> int:
        return self._w.foreground

    def BringWindowToTop(self, hwnd: int) -> None:
        self._w._call("BringWindowToTop", hwnd)

    def SetForegroundWindow(self, hwnd: int) -> None:
        self._w._call("SetForegroundWindow", hwnd)


class _Process:
    def __init__(self, windows: _Windows) -> None:
        self._w = windows

    def GetWindowThreadProcessId(self, hwnd: int) -> tuple[int, int]:
        return (MY_THREAD if hwnd == 0 else THEIR_THREAD), 1234

    def AttachThreadInput(self, mine: int, theirs: int, attach: bool) -> None:
        self._w._call("AttachThreadInput", mine, theirs, attach)


class _Api:
    def GetCurrentThreadId(self) -> int:
        return MY_THREAD


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> _Windows:
    state = _Windows()
    monkeypatch.setattr(win32, "win32gui", _Gui(state))
    monkeypatch.setattr(win32, "win32process", _Process(state))
    monkeypatch.setattr(win32, "win32api", _Api())
    return state


def _names(windows: _Windows) -> list[object]:
    return [call[0] for call in windows.calls]


def test_every_call_going_through_reports_no_refusal(windows: _Windows) -> None:
    assert win32.request_foreground(TARGET) == []
    assert windows.calls == [
        ("AttachThreadInput", MY_THREAD, THEIR_THREAD, True),
        ("BringWindowToTop", TARGET),
        ("SetForegroundWindow", TARGET),
        ("AttachThreadInput", MY_THREAD, THEIR_THREAD, False),
    ]


def test_a_refused_bring_window_to_top_still_tries_set_foreground_window(
    windows: _Windows,
) -> None:
    windows.refuse["BringWindowToTop"] = _denied("BringWindowToTop")

    refused = win32.request_foreground(TARGET)

    assert ("SetForegroundWindow", TARGET) in windows.calls
    assert windows.calls[-1] == ("AttachThreadInput", MY_THREAD, THEIR_THREAD, False)
    assert refused == ["BringWindowToTop (Access is denied)"]


def test_a_refused_attach_still_tries_both_calls_and_detaches_nothing(
    windows: _Windows,
) -> None:
    windows.refuse["AttachThreadInput"] = _denied("AttachThreadInput")

    refused = win32.request_foreground(TARGET)

    assert _names(windows) == [
        "AttachThreadInput",
        "BringWindowToTop",
        "SetForegroundWindow",
    ]
    assert refused == ["AttachThreadInput (Access is denied)"]


def test_every_refusal_is_reported_in_the_order_tried(windows: _Windows) -> None:
    windows.refuse["BringWindowToTop"] = _denied("BringWindowToTop")
    windows.refuse["SetForegroundWindow"] = win32.Win32Error(
        0, "SetForegroundWindow", "No error message is available"
    )

    refused = win32.request_foreground(TARGET)

    assert refused == [
        "BringWindowToTop (Access is denied)",
        "SetForegroundWindow (no error code)",
    ]
    assert windows.calls[-1] == ("AttachThreadInput", MY_THREAD, THEIR_THREAD, False)


def test_no_attach_when_this_thread_owns_the_foreground_or_there_is_none(
    windows: _Windows,
) -> None:
    windows.foreground = 0

    assert win32.request_foreground(TARGET) == []
    assert _names(windows) == ["BringWindowToTop", "SetForegroundWindow"]


def test_a_minimised_window_is_restored_first(windows: _Windows) -> None:
    windows.iconic = True

    win32.request_foreground(TARGET)

    assert windows.calls[0] == ("ShowWindow", TARGET, win32.win32con.SW_RESTORE)
