"""`find_window`: the one visible window of a class, owned by a named executable."""

from dataclasses import dataclass

import pytest

from botting.screen import MultipleWindows, WindowNotFound, find_window
from botting.screen import _win32 as win32

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
