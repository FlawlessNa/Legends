"""
Where a mouse move lands: client-area points, in physical pixels, at any scale.

The stubbed Win32 answers the way Windows answers a per-monitor-DPI-aware (v2)
process: every coordinate physical. A screen at scale `s` shows `W/s x H/s`
logical pixels, but the bot never sees those, so nothing in the mapping may
depend on `s` - which is what these tests pin.
"""

import asyncio
import ctypes

import pytest
from pytest_mock import MockerFixture

import botting  # noqa: F401 - importing it is what declares DPI awareness
from botting.controller import high_level

SCALES = [1.0, 1.25, 1.5]
SCREENS = [(1920, 1080), (2560, 1440)]


def _absolute(point: tuple[int, int], screen: tuple[int, int]) -> tuple[int, int]:
    return point[0] * 65536 // screen[0], point[1] * 65536 // screen[1]


@pytest.fixture
def sent(mocker: MockerFixture) -> list[tuple[int, int]]:
    """The absolute points `mouse_move` hands to input construction."""
    points: list[tuple[int, int]] = []

    def _construct(handle: int, keys: list[tuple[int, int]], events: object) -> list:
        points.extend(keys)
        return []

    mocker.patch.object(high_level, "input_constructor", side_effect=_construct)
    mocker.patch.object(high_level, "focused_inputs", new=mocker.AsyncMock())
    # The window rectangle includes the border and title bar; the client area
    # is what a Frame shows, so a move must never be placed from it.
    mocker.patch.object(
        high_level.win32gui, "GetWindowRect", side_effect=AssertionError
    )
    return points


def _stub_screen(
    mocker: MockerFixture,
    screen: tuple[int, int],
    client_origin: tuple[int, int],
) -> None:
    metrics = {0: screen[0], 1: screen[1]}  # SM_CXSCREEN, SM_CYSCREEN
    mocker.patch.object(
        high_level.win32api, "GetSystemMetrics", side_effect=metrics.__getitem__
    )
    mocker.patch.object(
        high_level.win32gui,
        "ClientToScreen",
        side_effect=lambda hwnd, p: (client_origin[0] + p[0], client_origin[1] + p[1]),
    )
    mocker.patch.object(high_level.win32api, "GetCursorPos", return_value=(0, 0))


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("screen", SCREENS)
def test_client_point_lands_on_its_screen_point(
    mocker: MockerFixture,
    sent: list[tuple[int, int]],
    scale: float,
    screen: tuple[int, int],
) -> None:
    # The client's origin sits at the same logical place on every screen, so
    # its physical position grows with the scale, as it does on Windows.
    origin = (round(160 * scale), round(90 * scale))
    _stub_screen(mocker, screen, origin)
    target = (683, 384)  # a client-area point, as a Frame's pixels give it

    asyncio.run(high_level.mouse_move(1, target, total_duration=0))

    expected = (origin[0] + target[0], origin[1] + target[1])
    assert sent == [_absolute(expected, screen)]


@pytest.mark.parametrize("screen", SCREENS)
def test_a_trajectory_ends_on_the_client_point(
    mocker: MockerFixture, sent: list[tuple[int, int]], screen: tuple[int, int]
) -> None:
    origin = (200, 100)
    _stub_screen(mocker, screen, origin)

    asyncio.run(high_level.mouse_move(1, (400, 300), total_duration=0.5))

    assert sent[-1] == _absolute((600, 400), screen)


def test_screen_size_is_read_at_each_call(mocker: MockerFixture) -> None:
    metrics = mocker.patch.object(high_level.win32api, "GetSystemMetrics")
    metrics.side_effect = [1920, 1080, 2560, 1440]
    assert high_level.screen_size() == (1920, 1080)
    assert high_level.screen_size() == (2560, 1440)


def test_importing_botting_declares_per_monitor_dpi_awareness_v2() -> None:
    user32 = ctypes.windll.user32
    user32.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.AreDpiAwarenessContextsEqual.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    current = user32.GetThreadDpiAwarenessContext()
    per_monitor_v2 = ctypes.c_void_p(-4)
    assert user32.AreDpiAwarenessContextsEqual(current, per_monitor_v2)
