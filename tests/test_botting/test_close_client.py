"""
`close_client` against a throwaway process that owns a window, never the game:
the process ends, and its window is gone.
"""

import subprocess
import sys
from collections.abc import Iterator

import pytest

from botting.screen import ClientNotClosed, close_client
from botting.screen import _win32 as win32

# A child that creates a hidden top-level window, prints its handle, and pumps
# messages until it is ended.
_WINDOW_OWNER = """
import win32api, win32gui
wc = win32gui.WNDCLASS()
wc.lpszClassName = "LegendsCloseClientTest"
wc.lpfnWndProc = {}
wc.hInstance = win32api.GetModuleHandle(None)
atom = win32gui.RegisterClass(wc)
hwnd = win32gui.CreateWindow(atom, "throwaway", 0, 0, 0, 10, 10, 0, 0, wc.hInstance, None)
print(hwnd, flush=True)
win32gui.PumpMessages()
"""


@pytest.fixture
def owner() -> Iterator[tuple[subprocess.Popen[str], int]]:
    process = subprocess.Popen(
        [sys.executable, "-c", _WINDOW_OWNER], stdout=subprocess.PIPE, text=True
    )
    try:
        assert process.stdout is not None
        hwnd = int(process.stdout.readline())
        yield process, hwnd
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


def test_the_owning_process_ends_and_its_window_is_gone(
    owner: tuple[subprocess.Popen[str], int],
) -> None:
    process, hwnd = owner
    assert win32.is_window(hwnd)
    assert process.poll() is None

    close_client(hwnd)

    assert not win32.is_window(hwnd)
    assert process.wait(timeout=5) is not None


def test_a_window_already_gone_is_closed_already(
    owner: tuple[subprocess.Popen[str], int],
) -> None:
    process, hwnd = owner
    process.kill()
    process.wait(timeout=10)

    close_client(hwnd)

    assert not win32.is_window(hwnd)


# --- the race, at the Win32 seam -------------------------------------------------------


def _desktop(
    monkeypatch: pytest.MonkeyPatch, *, lingers: int, problem: str | None
) -> None:
    """A window that is still a window for `lingers` more looks, whose process
    `terminate_window_process` reports `problem` about."""
    looks = iter([True] * (lingers + 1))
    monkeypatch.setattr(win32, "is_window", lambda hwnd: next(looks, False))
    monkeypatch.setattr(
        win32, "terminate_window_process", lambda hwnd, code, ms: problem
    )


def test_a_process_already_ending_whose_window_then_goes_is_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its window outlives it for a moment, so it can't be ended any more."""
    _desktop(monkeypatch, lingers=3, problem="process 7 can't be ended: error 5")

    close_client(1, timeout=1.0)


def test_a_window_that_stays_is_not_closed_and_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(win32, "is_window", lambda hwnd: True)
    monkeypatch.setattr(
        win32, "terminate_window_process", lambda hwnd, code, ms: "error 5"
    )

    with pytest.raises(ClientNotClosed, match="error 5"):
        close_client(1, timeout=0.1)
