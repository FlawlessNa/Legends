"""
The `windll.user32` seam: which entry points are exported, and the two helpers
that turn a key name into a virtual-key code.

`_get_virtual_key` and `_keyboard_layout_handle` are only meaningful against a
real keyboard layout, so the tests covering them load layouts into the machine
and cycle through them. That side effect is machine-global, not process-local,
which is why they carry the `system` marker and stay out of the default run.
"""

import ctypes
import string
from collections.abc import Callable, Iterator

import pytest
import win32gui

from botting.controller.inputs.inputs_helpers import (
    _get_virtual_key,
    _keyboard_layout_handle,
    _setup_exported_functions,
)

HKL_NEXT = 1

#: The layouts cycled through to prove a virtual-key code doesn't depend on the
#: active one. ENG-US and CAN-CMS are left loaded on teardown - they are the two
#: a developer machine here is expected to have already.
LAYOUTS = {
    "ENG-US": "00000409",
    "ENG-UK": "00000809",
    "FRA-FR": "0000040c",
    "CAN-CMS": "00011009",
    "CAN-FR": "00001009",
}
KEPT_LOADED = ("ENG-US", "CAN-CMS")


# --- The exported user32 entry points ---------------------------------------


def test_setup_exported_functions_exports_the_five_user32_entry_points() -> None:
    exported = _setup_exported_functions()

    assert set(exported) == {
        "MapVirtualKeyExW",
        "GetWindowThreadProcessId",
        "GetKeyboardLayout",
        "PostMessageW",
        "SendInput",
    }
    assert all(callable(func) for func in exported.values())


# --- The virtual-key helpers, against real layouts --------------------------


@pytest.fixture(scope="module")
def cycled_layouts() -> Iterator[Callable[[], None]]:
    """
    Loads every layout in `LAYOUTS`, then puts the machine back as it was.

    Yields a callable that advances to the next loaded layout, so a test can
    assert a property holds across all of them.
    """
    user32 = ctypes.windll.user32
    name = ctypes.create_unicode_buffer(10)
    user32.GetKeyboardLayoutNameW(name)
    original = name.value

    # Unloading takes the HKL the load returned, not the layout string.
    handles = {
        key: user32.LoadKeyboardLayoutW(code, 0) for key, code in LAYOUTS.items()
    }

    def _next_layout() -> None:
        user32.ActivateKeyboardLayout(HKL_NEXT, 0)

    yield _next_layout

    for key, handle in handles.items():
        if key not in KEPT_LOADED:
            user32.UnloadKeyboardLayout(handle)

    # Bounded: a layout that never comes back around must not hang the suite.
    for _ in range(len(LAYOUTS) + 1):
        user32.GetKeyboardLayoutNameW(name)
        if name.value == original:
            break
        user32.ActivateKeyboardLayout(HKL_NEXT, 0)


@pytest.fixture
def foreground_handle() -> int:
    return win32gui.GetForegroundWindow()


@pytest.mark.system
def test_virtual_key_is_the_same_code_whatever_the_active_layout(
    cycled_layouts: Callable[[], None], foreground_handle: int
) -> None:
    """The property the input layer depends on: a key name maps to one code."""
    for _ in LAYOUTS:
        cycled_layouts()
        layout = _keyboard_layout_handle(foreground_handle)

        for char in string.ascii_letters:
            assert _get_virtual_key(char, True, layout) == ord(char)
            assert _get_virtual_key(char, False, layout) == ord(char.upper())
        for char in string.digits:
            assert _get_virtual_key(char, False, layout) == ord(char)
        for char in string.punctuation:
            assert _get_virtual_key(char, True, layout) == ord(char)


@pytest.mark.system
def test_layout_handle_is_pinned_per_window_once_looked_up(
    cycled_layouts: Callable[[], None], foreground_handle: int
) -> None:
    """
    The lookup is `lru_cache`d on the handle, so one window keeps one layout for
    the life of the process even if the user switches language mid-session.
    """
    pinned = _keyboard_layout_handle(foreground_handle)

    for _ in LAYOUTS:
        cycled_layouts()
        assert _keyboard_layout_handle(foreground_handle) == pinned
