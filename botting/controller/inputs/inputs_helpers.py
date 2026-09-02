"""
Exports the necessary functions from windll.user32 to be used by the input module.
Retrieves appropriate virtual key code given keyboard layout and key name.
"""

import asyncio
import ctypes
import random
import time
from collections.abc import Callable, Generator
from ctypes import wintypes
from functools import lru_cache
from typing import Any

import win32api
import win32con

from .timer_resolution import raise_timer_resolution

# http://www.kbdedit.com/manual/low_level_vk_list.html
# https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes

__all__ = [
    "DELAY",
    "EXTENDED_KEYS",
    "KEYBOARD_MAPPING",
    "MAPVK_VK_TO_VSC_EX",
    "OVERHEAD",
    "TYPEMATIC_DELAY",
    "TYPEMATIC_REPEAT",
    "_EXPORTED_FUNCTIONS",
    "_get_virtual_key",
    "_keyboard_layout_handle",
    "_setup_exported_functions",
    "random_delay",
    "typematic_delay",
]

DELAY: float = 0.033 - time.get_clock_info("monotonic").resolution
# DELAY: float = 0.033


def _random_delay() -> Generator[float]:
    while True:
        new_val = random.uniform(0.95, 1.05)
        yield new_val * DELAY


random_delay = _random_delay()

# Before OVERHEAD is measured, never after: the constant has to describe the same
# timer regime the send loop will spend it in. See `timer_resolution`.
raise_timer_resolution()


def _measure_send_loop_overhead(iterations: int = 50) -> float:
    """
    The per-Step cost the send loop pays on top of the delay it asked for.

    Measured the way `focused_inputs` pays it: many `asyncio.sleep`s inside
    **one already-running loop**. The previous measurement ran
    `asyncio.run(...)` per iteration and so charged every Step a whole event
    loop's startup and teardown - a cost the send loop pays once per Action, if
    at all. On this machine that inflated the constant from ~0.5ms to ~11.5ms.

    The first sleep is discarded: a freshly-created loop pays one-off costs on
    it that no later Step sees.

    **Mean, not median**, though the median is measurably the steadier of the
    two run to run (~0.33ms of spread against ~0.45ms). `duration` spends this
    as `OVERHEAD * len(delays)` - a *sum* over Steps - and the excess is
    right-skewed, outliers only ever running long. The mean is the estimator
    that makes that sum unbiased; the median would under-predict every
    multi-Step sequence in exchange for a tidier constant.

    Two things this deliberately leaves out, both small next to the sleep and
    neither measurable without a target window: `_send_input`'s `SendInput`
    syscall, and `HeldKeysLedger.record_step`.
    :param iterations: Sleeps to average over.
    :return: Mean excess of the actual gap over the requested delay, in seconds.
    """

    async def _measure() -> float:
        await asyncio.sleep(next(random_delay))

        requested = 0.0
        actual = 0.0
        for _ in range(iterations):
            delay = next(random_delay)
            start = time.perf_counter()
            await asyncio.sleep(delay)
            actual += time.perf_counter() - start
            requested += delay
        return (actual - requested) / iterations

    return asyncio.run(_measure())


OVERHEAD: float = _measure_send_loop_overhead()

# The client's typematic settings, read off Spy++ against a live game window (issue
# #99): a held key repeats every ~33ms, and the first repeat follows the press by
# ~500ms. Measured constants - Expectations in the invariant catalogue's sense, not
# anything derivable - and both describe **wall-clock** spacing.
TYPEMATIC_REPEAT: float = 0.033
TYPEMATIC_DELAY: float = 0.5


def _typematic_delay() -> Generator[float]:
    """
    Delays that put consecutive repeat Steps `TYPEMATIC_REPEAT` apart on the wall clock.

    `random_delay` asks for 33ms and the send loop then spends `OVERHEAD` on top of it,
    so the gap the game actually sees is 33ms + OVERHEAD - which matches no Windows
    typematic setting, the range being ~31ms to 500ms. Spending `OVERHEAD` out of the
    interval instead of adding to it makes the *observable* spacing the constant, which
    is what **B6 Repeat Cadence** is stated over.

    Clamped at zero: `OVERHEAD` is measured per machine and nothing guarantees it stays
    under 33ms, and **A5 Delays** requires every delay to be non-negative.
    """
    while True:
        yield random.uniform(0.95, 1.05) * max(TYPEMATIC_REPEAT - OVERHEAD, 0.0)


typematic_delay = _typematic_delay()

KEYBOARD_MAPPING = {
    "alt": win32con.VK_MENU,
    # Or win32con.VK_RMENU, but Spy++ shows that the game uses the VK_MENU instead.
    "alt_right": win32con.VK_MENU,
    # Or win32con.VK_LCONTROL, but Spy++ shows that the game uses the VK_CONTROL instead.
    "ctrl": win32con.VK_CONTROL,
    # Or win32con.VK_RCONTROL, but Spy++ shows that the game uses the VK_CONTROL instead.
    "ctrl_right": win32con.VK_CONTROL,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "shift": win32con.VK_SHIFT,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "insert": win32con.VK_INSERT,
    "delete": win32con.VK_DELETE,
    "pageup": win32con.VK_PRIOR,
    "pagedown": win32con.VK_NEXT,
    "num_lock": win32con.VK_NUMLOCK,
    "space": win32con.VK_SPACE,
    "enter": win32con.VK_RETURN,
    "tab": win32con.VK_TAB,
    "escape": win32con.VK_ESCAPE,
}

EXTENDED_KEYS = (
    "alt_right",
    "ctrl_right",
    "insert",
    "home",
    "pageup",
    "delete",
    "end",
    "pagedown",
    "left",
    "right",
    "up",
    "down",
    "num_lock",
    "break",
    "print_screen",
    "divide",
    "enter",
    "num_lock",
)

MAPVK_VK_TO_VSC = 0
MAPVK_VSC_TO_VK = 1
MAPVK_VK_TO_CHAR = 2
MAPVK_VSC_TO_VK_EX = 3
MAPVK_VK_TO_VSC_EX = 4

# pywin32 ships no type for the layout handle, so `VkKeyScanEx` arrives partially
# unknown and every call site inherits that. Narrowed once here, at the boundary,
# to the signature `_get_virtual_key` actually relies on - the module is taken as
# `Any` so the gap is closed by a declaration rather than by a suppression.
_win32api: Any = win32api
_vk_key_scan_ex: Callable[[str, Any], int] = _win32api.VkKeyScanEx


def _setup_exported_functions() -> dict[str, Callable[..., Any]]:
    """
    :return: Dictionary of exported functions from the ctypes.windll module.
    """
    map_virtual_key = ctypes.windll.user32.MapVirtualKeyExW
    map_virtual_key.restype = wintypes.UINT
    map_virtual_key.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HKL]

    get_window_thread_process_id = ctypes.windll.user32.GetWindowThreadProcessId
    get_window_thread_process_id.restype = wintypes.DWORD
    get_window_thread_process_id.argtypes = [wintypes.HWND, wintypes.LPDWORD]

    get_keyboard_layout = ctypes.windll.user32.GetKeyboardLayout
    get_keyboard_layout.restype = wintypes.HKL
    get_keyboard_layout.argtypes = [wintypes.DWORD]

    post_message = ctypes.windll.user32.PostMessageW
    post_message.restype = wintypes.BOOL
    post_message.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]

    # Note - The argtypes of SendInput is defined in each function call,
    # since the array length may change at each call.
    send_input = ctypes.windll.user32.SendInput
    send_input.restype = wintypes.UINT

    return {
        "MapVirtualKeyExW": map_virtual_key,
        "GetWindowThreadProcessId": get_window_thread_process_id,
        "GetKeyboardLayout": get_keyboard_layout,
        "PostMessageW": post_message,
        "SendInput": send_input,
    }


_EXPORTED_FUNCTIONS = _setup_exported_functions()


def _get_virtual_key(key: str, case_sensitive: bool, layout: wintypes.HKL) -> int:
    """
    :param key: String representation of the key to be pressed.
    :param layout: Handle to the keyboard layout of the window.
    :return: Virtual key code associated with the key.
    """
    if len(key) == 1 and case_sensitive:
        return ord(key)
    elif len(key) == 1:
        return win32api.LOBYTE(_vk_key_scan_ex(key, layout))
    else:
        return KEYBOARD_MAPPING[key]


@lru_cache
def _keyboard_layout_handle(hwnd: int) -> wintypes.HKL:
    """
    :param hwnd: Handle to the window to send the message to.
    :return: Handle to the keyboard layout of the window.
    """
    thread_id = _EXPORTED_FUNCTIONS["GetWindowThreadProcessId"](
        wintypes.HWND(hwnd), None
    )
    return _EXPORTED_FUNCTIONS["GetKeyboardLayout"](thread_id)
