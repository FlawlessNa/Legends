"""
Low-level module that handles sending inputs to the focused window through SendInput().
"""
import asyncio
import ctypes
import itertools
import logging
import time
import win32con

from ctypes import wintypes
from typing import Literal
from win32com.client import Dispatch
from win32api import GetKeyState
from win32gui import SetForegroundWindow, GetForegroundWindow

from .inputs_helpers import (
    _EXPORTED_FUNCTIONS,
    _get_virtual_key,
    _keyboard_layout_handle,
    EXTENDED_KEYS,
    MAPVK_VK_TO_VSC_EX,
)
from .shared_resources import SharedResources

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)

logger = logging.getLogger(__name__)


class MouseInputStruct(ctypes.Structure):
    """Contains information about a simulated mouse event."""

    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KeyBdInputStruct(ctypes.Structure):
    """Contains information about a simulated keyboard event."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HardwareInputStruct(ctypes.Structure):
    """
    Contains information about a simulated message generated
    by an input device other than a keyboard or mouse.
    Not Implemented.
    """

    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class CombinedInput(ctypes.Union):
    """Contains information about a simulated event of any kind."""

    _fields_ = [
        ("ki", KeyBdInputStruct),
        ("mi", MouseInputStruct),
        ("hi", HardwareInputStruct),
    ]


class Input(ctypes.Structure):
    """
    Used by SendInput to store information for synthesizing input events
    such as keystrokes, mouse movement, and mouse clicks.
    """

    _fields_ = [("type", wintypes.DWORD), ("structure", CombinedInput)]


InputArray = Input * 1


MOUSE = wintypes.DWORD(0)
KEYBOARD = wintypes.DWORD(1)
HARDWARE = wintypes.DWORD(2)


def activate(hwnd: int) -> None:
    """
    Activates the window associated with the handle.
    Any key press or mouse click will be sent to the active window.
    :return: None
    """
    if GetForegroundWindow() != hwnd:
        logger.debug(f"Activating window {hwnd}")
        shell = Dispatch("WScript.Shell")
        shell.SendKeys("%")
        SetForegroundWindow(hwnd)


@SharedResources.requires_focus
async def focused_inputs(
    hwnd: int,
    inputs: list[tuple],
    delays: list[float],
    keys_to_release: tuple | None,
) -> None:
    """
    Sends the inputs to the active window.
    A small delay is added between each input.
    :param hwnd: handle to the window to send the inputs to.
    :param inputs: input structures to send.
    :param delays: delays between each input.
    :param keys_to_release: Ensures that the keys are released after the inputs are sent
    :return: None
    """
    cleanup = False
    try:
        activate(hwnd)

        for i in range(len(inputs)):
            _send_input(inputs[i])
            await asyncio.sleep(delays[i])

        if keys_to_release:
            _send_input(keys_to_release)
            cleanup = True

    except Exception as e:
        raise e
    finally:
        if keys_to_release and not cleanup:
            if len(delays) > 1 or delays[0] != 0.5:
                time.sleep(min(delays))
            _send_input(keys_to_release)


def _send_input(structure: tuple) -> None:
    """
    Sends the input structure to the active window.
    :param structure: A single input structure.
    :return:
    """
    failure_count = 0
    array_class = Input * structure[0].value
    pointer = ctypes.POINTER(array_class)
    _EXPORTED_FUNCTIONS["SendInput"].argtypes = [wintypes.UINT, pointer, wintypes.INT]
    while _EXPORTED_FUNCTIONS["SendInput"](*structure) != structure[0].value:
        logger.error(f"Failed to send input {structure}")
        failure_count += 1
        if failure_count > 10:
            logger.critical(f"Unable to send structure {structure} to active window")
            raise RuntimeError(f"Unable to send structure {structure} to active window")


def full_input_constructor(
    hwnd: int,
    keys: list[list[str]],
    events: list[list[Literal["keydown", "keyup"] | str]],
    as_unicode: bool = False,
) -> list[tuple]:
    """
    Constructs the input structures for the given keys and events.
    :param hwnd: Handle to the window to send the inputs to.
    :param keys: Keystrokes to send.
    :param events: Keydown or Keyup events.
    :param as_unicode: Used for typewriting only.
    :return:
    """

    structures = []
    for lst_key, lst_event in zip(keys, events):
        assert len(lst_key) == len(lst_event)
        inputs = []
        num_inputs = len(lst_key)
        array_class = Input * num_inputs
        array_pointer = ctypes.POINTER(array_class)
        for key, event in zip(lst_key, lst_event):
            inputs.append(_single_input_constructor(hwnd, key, event, as_unicode))
        input_array = array_class(*inputs)
        structures.append(
            (
                wintypes.UINT(num_inputs),
                array_pointer(input_array),
                wintypes.INT(ctypes.sizeof(input_array[0]))
            )
        )
    return structures


def full_input_mouse_constructor(
    x_trajectory: list[int | None],
    y_trajectory: list[int | None],
    events: list[Literal["click", "down", "up"] | None],
    mouse_data: list[int | None],
) -> list[tuple]:
    """
    Constructs the input structures for the given mouse events.
    :param x_trajectory: X coordinates of mouse trajectory.
    :param y_trajectory: Y coordinates of mouse trajectory.
    :param events: Any click events.
    :param mouse_data: Only Used for mouse scroll. Set to 0 otherwise.
    :return:
    """
    return_val = []
    input_array_class = Input * 1
    input_pointer = ctypes.POINTER(input_array_class)

    for x, y, event, mouse in itertools.zip_longest(
        x_trajectory, y_trajectory, events, mouse_data
    ):
        input_structure = _single_input_mouse_constructor(x, y, event, mouse)
        input_array = input_array_class(input_structure)
        return_val.append(
            (
                    wintypes.UINT(1),
                    input_pointer(input_array),
                    wintypes.INT(ctypes.sizeof(input_structure)),
                ),
        )
    return return_val


def _single_input_constructor(
    hwnd: int,
    key: str,
    event: Literal["keydown", "keyup"],
    as_unicode: bool = False,
) -> Input:
    """
    Constructs a single input structure for the given key and event.
    :param hwnd:
    :param key:
    :param event:
    :param as_unicode:
    :return:
    """
    assert isinstance(key, str) and isinstance(event, str)
    assert event in ["keyup", "keydown"], f"Event type {event} is not supported"
    flags = KEYEVENTF_EXTENDEDKEY if key in EXTENDED_KEYS else 0
    vk_key = _get_virtual_key(key, False, _keyboard_layout_handle(hwnd))
    if as_unicode:
        assert (
                len(key) == 1
        ), f"Key {key} must be a single character when as_unicode=True"
        scan_code = _get_virtual_key(key, True, _keyboard_layout_handle(hwnd))
        vk_key = 0
        flags |= KEYEVENTF_UNICODE
    else:
        scan_code = _EXPORTED_FUNCTIONS["MapVirtualKeyExW"](
            vk_key,
            MAPVK_VK_TO_VSC_EX,
            _keyboard_layout_handle(hwnd),
        )
    flags = flags | KEYEVENTF_KEYUP if event == "keyup" else flags

    keybd_input = KeyBdInputStruct(
        wintypes.WORD(vk_key),
        wintypes.WORD(scan_code),
        wintypes.DWORD(flags),
        wintypes.DWORD(0),
        None,
    )
    input_struct = Input(type=KEYBOARD, structure=CombinedInput(ki=keybd_input))
    return input_struct


def _single_input_mouse_constructor(
    x: int | None,
    y: int | None,
    event: Literal["click", "down", "up"] | None,
    mouse_data: int | None,
) -> Input:
    """
    :param x: Absolute X target mouse cursor position.
    :param y: Absolute Y target mouse cursor position.
    :param event: Whether the event is a click, down or up, or nothing.
    :param mouse_data: Set to 0 unless mouse scroll is used.
    :return:
    """
    if mouse_data is None:
        mouse_data = 0
    flags = 0
    if x is not None and y is not None:
        flags = MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_MOVE
    else:
        x = 0
        y = 0

    if event is not None:
        if event == "click":
            flags |= MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP
        elif event == "down":
            flags |= MOUSEEVENTF_LEFTDOWN
        elif event == "up":
            flags |= MOUSEEVENTF_LEFTUP
        else:
            raise ValueError(f"Event {event} is not supported.")

    assert flags != 0, f"Either x, y or event must be provided."
    mouse_input = MouseInputStruct(
        wintypes.LONG(x),
        wintypes.LONG(y),
        wintypes.DWORD(mouse_data),
        wintypes.DWORD(flags),
        wintypes.DWORD(0),
        None,
    )
    input_struct = Input(type=MOUSE, structure=CombinedInput(mi=mouse_input))
    return input_struct


def repeat_inputs(keys, events, delays, duration, central_delay, delay_gen) -> None:
    """
    Repeats the inputs for the given duration. Used for automatic repeat feature of
    the keyboard.
    """
    upper_bound = int((duration - sum(delays)) // central_delay)
    if upper_bound > 0:
        repeated_key = keys[-1][-1]
        keys.extend([[repeated_key]] * upper_bound)
        events.extend([["keydown"]] * upper_bound)
        delays_to_add = len(events) - len(delays)
        delays.extend([next(delay_gen) for _ in range(delays_to_add)])


def move_params_validator(
    direction: Literal["up", "down", "left", "right"],
    secondary_direction: Literal["up", "down", "left", "right"] | None,
    duration: float,
    central_delay: float,
    jump: bool,
    jump_interval: float,
    secondary_key_press: str | None,
    secondary_key_interval: float,
    tertiary_key_press: str | None,
    combine_jump_secondary: bool | None,
) -> None:
    """
    Validates the parameters for the move function, since it is a complex function.
    """
    assert direction in ["up", "down", "left", "right"]
    assert secondary_direction in [None, "up", "down", "left", "right"]
    assert duration > 0 and central_delay > 0
    assert jump_interval >= 0
    assert secondary_key_interval >= 0

    # Used for Flash Jumping (combined is false) or attack + jump (combine is true)
    if jump and secondary_key_press:
        assert jump_interval == secondary_key_interval
        assert jump_interval > 0
        assert combine_jump_secondary is not None

    # Strictly used for telecast
    if tertiary_key_press:
        assert not secondary_direction and not jump
        assert secondary_key_press is not None
        assert secondary_key_interval > 0

    # Strictly used for Flash Jumping into a rope (combine is false)
    if secondary_direction and jump and secondary_key_press:
        assert combine_jump_secondary is False


def _remove_num_lock() -> None:
    """
    Removes the num lock if it is on.
    :return:
    """
    if GetKeyState(win32con.VK_NUMLOCK) != 0:
        logger.info("NumLock is on. Turning it off.")
        array_class = Input * 2
        array_pointer = ctypes.POINTER(array_class)
        _input = [
            _single_input_constructor(GetForegroundWindow(), "num_lock", "keydown"),
            _single_input_constructor(GetForegroundWindow(), "num_lock", "keyup"),
        ]

        input_array = array_class(*_input)
        _send_input((
            wintypes.UINT(2),
            array_pointer(input_array),
            wintypes.INT(ctypes.sizeof(input_array[0]))
        ))


_remove_num_lock()