"""
Low-level module that handles sending inputs to the focused window through SendInput().
"""
import asyncio
import ctypes
import logging
import win32con

from ctypes import wintypes
from typing import Literal
from win32com.client import Dispatch
from win32api import HIBYTE, GetKeyState, GetAsyncKeyState
from win32gui import SetForegroundWindow, GetForegroundWindow

from .shared_resources import SharedResources

from .inputs_helpers import (
    _EXPORTED_FUNCTIONS,
    _get_virtual_key,
    _keyboard_layout_handle,
    EXTENDED_KEYS,
    MAPVK_VK_TO_VSC_EX,
)

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

EVENTS = Literal["keydown", "keyup", "click", "mousedown", "mouseup"]
OPPOSITES = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


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


async def activate(hwnd: int) -> bool:
    """
    Activates the window associated with the handle.
    Any key press or mouse click will be sent to the active window.
    :return: None
    """
    acquired = False
    if GetForegroundWindow() != hwnd:
        acquired = await SharedResources.focus_lock.acquire()
        logger.debug(f"Activating window {hwnd}")
        # Before activating, make sure to release any keys that are currently pressed.
        _release_watched_keys(hwnd)

        shell = Dispatch("WScript.Shell")
        shell.SendKeys("%")
        SetForegroundWindow(hwnd)

    elif not acquired and not SharedResources.focus_lock.locked():
        acquired = await SharedResources.focus_lock.acquire()
    return acquired


def _release_watched_keys(hwnd: int) -> None:
    # TODO
    watched_keys = SharedResources.keys_sent
    move_keys = {
        win32con.VK_UP: "up",
        win32con.VK_DOWN: "down",
        win32con.VK_LEFT: "left",
        win32con.VK_RIGHT: "right",
    }
    release = [[]]
    events = [[]]
    for key in watched_keys:
        if HIBYTE(GetAsyncKeyState(key)) != 0:
            release[0].append(move_keys[key])
            events[0].append("keyup")
    if release[0]:
        inputs = input_constructor(hwnd, release, events)
        _send_input(inputs[0])


def release_opposites(hwnd: int, *keys: str | None) -> tuple:
    """
    Releases the opposite keys of the given keys, if they are held down.
    :param hwnd: Handle to the window to send the inputs to.
    :param keys: Movement keys to release.
    :return: Input structure to release the opposite keys.
    """
    release = []
    events: list[Literal] = []
    for key in keys:
        if (
            HIBYTE(
                GetAsyncKeyState(
                    _get_virtual_key(
                        OPPOSITES[key], False, _keyboard_layout_handle(hwnd)
                    )
                )
            )
            != 0
        ):
            release.append(OPPOSITES[key])
            events.append("keyup")
    if release:
        return input_constructor(hwnd, [release], [events])[0]


def input_constructor(
    hwnd: int,
    inputs: list[str | None | tuple[int, int] | list[str | None | tuple[int, int]]],
    events: list[EVENTS | list[EVENTS] | None],
    as_unicode: bool | list[bool] = False,
    mouse_data: list[int | None] | None = None,
) -> list[tuple]:
    """
    Constructs the input structures for the given inputs and events.
    These must be of the same length. When an item in inputs is a list, the
    corresponding item in events must also be a list. Those are considered as a single
    input array for the purpose of SendInput, so they are sent simultaneously.
    :param hwnd: Handle to the window that will receive the inputs.
    :param inputs: keystrokes (str), mouse coordinates (tuple), None, or a list of those
    :param events: "keydown", "keyup", "click", "mousedown", "mouseup",
        or a list of those
    :param as_unicode: TODO
    :param mouse_data: TODO
    :return: Series of input structures to be sent to the active window with SendInput.
    """
    structures = []
    for lst_inputs, lst_events in zip(inputs, events):
        if isinstance(lst_inputs, list):
            assert isinstance(lst_events, list)
            assert len(lst_inputs) == len(lst_events)
            num_inputs = len(lst_inputs)
            array_class = Input * num_inputs
            array_pointer = ctypes.POINTER(array_class)
            inputs = [input_constructor(hwnd, inp, event, as_unicode, mouse_data) for inp, event in zip(lst_inputs, lst_events)]
            # for inp, event in zip(lst_inputs, lst_events):
            #     if isinstance(inp, str):
            #         inputs.append(
            #             _single_input_constructor(hwnd, inp, event, as_unicode)
            #         )
            #     else:
            #         inputs.append(
            #             _single_input_mouse_constructor(*inp, event, mouse_data)
            #         )
            input_array = array_class(*inputs)
            structures.append(
                (
                    wintypes.UINT(num_inputs),
                    array_pointer(input_array),
                    wintypes.INT(ctypes.sizeof(input_array[0])),
                )
            )
        else:
            if isinstance(lst_inputs, str):
                structures.append(
                    (
                        wintypes.UINT(1),
                        ctypes.POINTER(Input * 1)(
                            _single_input_constructor(
                                hwnd, lst_inputs, lst_events, as_unicode
                            )
                        ),
                        wintypes.INT(ctypes.sizeof(Input)),
                    )
                )
            else:
                if lst_inputs is None:
                    structures.append(
                        (
                            wintypes.UINT(1),
                            ctypes.POINTER(Input * 1)(
                                _single_input_mouse_constructor(
                                    None, None, lst_events, mouse_data
                                )
                            ),
                            wintypes.INT(ctypes.sizeof(Input)),
                        )
                    )
                else:
                    structures.append(
                        (
                            wintypes.UINT(1),
                            ctypes.POINTER(Input * 1)(
                                _single_input_mouse_constructor(
                                    *lst_inputs, lst_events, mouse_data
                                )
                            ),
                            wintypes.INT(ctypes.sizeof(Input)),
                        )
                    )
    return structures


async def focused_inputs(
    hwnd: int,
    inputs: list[tuple],
    delays: list[float],
    enforce_last_inputs: int = 0,
) -> int:
    """
    Sends the inputs to the active window.
    A small delay is added between each input.

    Whenever a direction is used in the input, it is always within the first input.
    Parse that input to see if any direction are used, and release opposite directions
    when necessary.
    If the 2nd input contains the same direction as the first, then the 0.5 delay is
    added as well.
    :param hwnd: handle to the window to send the inputs to.
    :param inputs: input structures to send.
    :param delays: delays between each input.
    :param enforce_last_inputs: Nbr of inputs at the end of input structure to enforce
    through a "finally" clause.
    :return: Nbr of inputs successfully sent.
    """
    res = 0
    keys_to_release: list[tuple] = []
    if enforce_last_inputs > 0:
        keys_to_release: list[tuple] = inputs[-enforce_last_inputs:]
        inputs = inputs[:-enforce_last_inputs]

    acquired = False
    try:
        acquired = await activate(hwnd)

        for i in range(len(inputs)):
            _send_input(inputs[i])
            res += 1
            await asyncio.sleep(delays[i])

    except asyncio.CancelledError:
        raise

    except Exception as e:
        raise e

    finally:
        if keys_to_release:
            for i in range(len(keys_to_release)):
                _send_input(keys_to_release[i])
                res += 1
        if acquired:
            SharedResources.focus_lock.release()
        return res


def get_held_movement_keys(hwnd: int) -> list[str]:
    """
    Returns a list of the currently held movement keys.
    :param hwnd:
    :return:
    """
    virtuals = {
        win32con.VK_UP: "up",
        win32con.VK_DOWN: "down",
        win32con.VK_LEFT: "left",
        win32con.VK_RIGHT: "right",
    }
    pressed = [
        key
        for key in OPPOSITES
        if HIBYTE(
            GetAsyncKeyState(
                _get_virtual_key(key, False, _keyboard_layout_handle(hwnd))
            )
        )
        != 0
    ]
    return pressed


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
    event: Literal["mousedown", "mouseup"] | None,
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
        if event == "mousedown":
            flags |= MOUSEEVENTF_LEFTDOWN
        elif event == "mouseup":
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
        _send_input(
            (
                wintypes.UINT(2),
                array_pointer(input_array),
                wintypes.INT(ctypes.sizeof(input_array[0])),
            )
        )


_remove_num_lock()
