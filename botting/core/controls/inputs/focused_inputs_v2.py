"""
Low-level module that handles sending inputs to the focused window through SendInput().
"""
import asyncio
import ctypes
import itertools
import logging
import random

from ctypes import wintypes
from typing import Literal
from win32com.client import Dispatch
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


async def _send_inputs(hwnd: int, inputs: list[list[tuple, float]]) -> None:
    """
    Activates the window associated with the handle and sends the required inputs.
    This requires window focus.
    An input structure may contain several inputs to be sent simultaneously
     (without any delay in between).
    If this is not desired, the enforce_delay parameter can be set to True
     (in higher-level API), and a delay will be enforced between each input.
    :param hwnd: Handle to the window to send the input to.
    :param inputs: list of list[tuple, float]. Each tuple contains the parameters
     to be sent to SendInput, and the float is delay after the input is sent.
     Note: When delays are not enforced, usually the list will be a single tuple,
      float, and float will be 0.0.
    :return: None
    """
    activate(hwnd)
    for item in inputs:
        input_structure, delay = item
        failure_count = 0
        input_array_class = Input * input_structure[0].value
        input_pointer = ctypes.POINTER(input_array_class)
        _EXPORTED_FUNCTIONS["SendInput"].argtypes = [
            wintypes.UINT,
            input_pointer,
            wintypes.INT,
        ]
        while (
            _EXPORTED_FUNCTIONS["SendInput"](*input_structure)
            != input_structure[0].value
        ):
            logger.error(f"Failed to send input {input_structure}")
            failure_count += 1

            # This will only be called if the input is not sent successfully.
            await asyncio.sleep(0.01)
            if failure_count > 10:
                logger.critical(
                    f"Unable to send the structure {input_structure} to the window {hwnd}"
                )
                raise RuntimeError(
                    f"Failed to send input {input_structure[0]} after 10 attempts."
                )
        # Allows for smaller delays between consecutive keys,
        # such as when writing a message in-game, or between KEYUP/KEYDOWN commands.
        if delay > 0:
            await asyncio.sleep(delay)


def _input_array_constructor(
    hwnd: int,
    keys: list[str],
    events: list[str],
    enforce_delay: bool,
    as_unicode: bool = False,
    delay: float = 0.033,
) -> list[list[tuple, float]]:
    """
    Constructs the input array of structures to be sent to the window associated
     the provided handle. Send that input through SendInput.
    When enforce_delay=True, N arrays of length 1 are created for each key/event pair,
     and a random delay is enforced between each key press.
    Otherwise, 1 array of length N is created (N == len(keys) == len(events)),
     and there is no delay as all inputs are sent simultaneously.
    :param hwnd: Handle to the window to send the input to.
    :param keys: list of string representation of the key(s) to be pressed.
    :param events: list of string Literals representing the type of event to be sent.
     Currently supported: 'keydown', 'keyup'.
    :param enforce_delay: bool. Whether to enforce a delay between each key press.
    :param as_unicode: bool. Whether to send the key as a unicode character or not.
     This is only used when sending a single key and allows to differentiate
     between lowercase uppercase.
    :param delay: The delay (which will be randomized slightly) between each key press
     when enforce_delay is True.
    :return: list of list[tuple, float]. Each tuple contains the parameters to be sent
     to SendInput, and the float is delay to be enforced after the input is sent.
    """

    assert isinstance(keys, list) and isinstance(
        events, list
    ), f"Keys and messages must be lists."
    assert len(keys) == len(
        events
    ), f"Msg and keys must have the same length when they are provided as lists."

    nbr_inputs = 1 if enforce_delay else len(keys)
    input_array_class = Input * nbr_inputs
    input_pointer = ctypes.POINTER(input_array_class)

    input_list = []
    for item in zip(keys, events):
        key, event = item
        input_list.append(_input_structure_constructor(hwnd, key, event, as_unicode))

    if enforce_delay:
        return_val = list()
        # Create N different arrays of length 1, each containing a single input structure.
        for item in input_list:
            input_single_array = input_array_class(item)
            full_params = tuple(
                [
                    wintypes.UINT(1),
                    input_pointer(input_single_array),
                    wintypes.INT(ctypes.sizeof(input_single_array[0])),
                ]
            )
            # Delay is randomized here to allow individual randomization between each input.
            return_val.append([full_params, random.uniform(delay * 0.95, delay * 1.05)])
        return return_val
    else:
        # Create 1 single array of length N. All inputs sent simultaneously.
        input_array = input_array_class(*input_list)
        full_input = [
            tuple(
                [
                    wintypes.UINT(nbr_inputs),
                    input_pointer(input_array),
                    wintypes.INT(ctypes.sizeof(input_array[0])),
                ]
            ),
            0.0,
        ]
        return [full_input]


def _input_structure_constructor(
    hwnd: int,
    key: str,
    event: Literal["keyup", "keydown"],
    as_unicode: bool = False,
) -> Input:
    """
    Constructs the input structure to be sent to the window associated the handle.
    Send that input through SendInput.
    :param hwnd: Handle to the window to send the input to.
    :param key: String representation of the key to be pressed.
    :param event: Whether the event is a keyup or keydown.
    :param as_unicode: bool. Whether to send the key as a unicode character or not.
     This is only used when sending a single key and allows to differentiate
      between lowercase uppercase.
    :return: Input structure.
    """
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