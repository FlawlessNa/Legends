"""
Low-level module that handles sending inputs to the focused window through SendInput().
"""

import asyncio
import ctypes
import logging
import win32con

from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Literal, Generator
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
    OVERHEAD,
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
OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}


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


@dataclass
class KeyboardInputWrapper:
    """
    Dataclass that stores the input structure and the delay to wait before sending
    the next input.
    """

    handle: int
    keys: list[str | list[str]] = field(default_factory=list)
    events: list[EVENTS | list[EVENTS]] = field(default_factory=list)
    delays: list[float] = field(default_factory=list)
    forced_key_releases: list[str] = field(default_factory=list)

    @property
    def c_input(self) -> list[tuple]:
        return input_constructor(self.handle, self.keys, self.events)

    @property
    def duration(self) -> float:
        return sum(self.delays) + OVERHEAD * len(self.delays)

    def append(
        self, keys: str | list[str], events: EVENTS | list[EVENTS], delay: float
    ) -> None:
        self.keys.append(keys)
        self.events.append(events)
        self.delays.append(delay)

    def fill(self, key: str, event: EVENTS, delay_generator: Generator, limit: float):
        """
        Fills the structure with the given key and event until the duration reaches the
        limit.
        :param key:
        :param event:
        :param delay_generator:
        :param limit:
        :return:
        """
        while self.duration < limit:
            self.append(key, event, next(delay_generator))

    @property
    def keys_held(self) -> set[str]:
        """
        Introspects the input structures to find the keys for which a KEYDOWN event is
        sent and for which no subsequent KEYUP event is sent.
        :return:
        """
        keys_down = set()
        for i, key in enumerate(self.keys):
            if isinstance(key, list):
                for j, k in enumerate(key):
                    if self.events[i][j] == "keydown":
                        keys_down.add(k)
                    elif self.events[i][j] == "keyup":
                        keys_down.discard(k)
            else:
                if self.events[i] == "keydown":
                    keys_down.add(key)
                elif self.events[i] == "keyup":
                    keys_down.discard(key)
        return keys_down

    async def send(self):
        return await focused_inputs(
            self.handle, self.c_input, self.delays, self.forced_key_releases
        )

    # def cancelled_callback(self, future):
    #     breakpoint()
    #     if future.cancelled():
    #         logger.debug(f"Cancelled callback called for {self}")
    #         forced_key_releases = list(self.keys_held)
    #         logger.debug(f"Keys to release: {forced_key_releases}")
    #
    def truncate(self, limit: float) -> "KeyboardInputWrapper":
        result = KeyboardInputWrapper(
            self.handle, forced_key_releases=self.forced_key_releases
        )
        generator = zip(self.keys, self.events, self.delays)
        while result.duration < limit:
            try:
                key, event, delay = next(generator)
                result.append(key, event, delay)
            except StopIteration:
                break
        return result


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
        release_all(GetForegroundWindow())
        Dispatch("WScript.Shell").SendKeys("%")
        SetForegroundWindow(hwnd)

    elif not acquired and not SharedResources.focus_lock.locked():
        acquired = await SharedResources.focus_lock.acquire()
    return acquired


def release_all(hwnd: int = None) -> None:
    if hwnd is None:
        hwnd = GetForegroundWindow()
    keys_to_release = []
    for key in SharedResources.keys_sent:
        if (
            HIBYTE(
                GetAsyncKeyState(
                    _get_virtual_key(key, True, _keyboard_layout_handle(hwnd))
                )
            )
            != 0
        ):
            keys_to_release.append(key)
    if keys_to_release:
        logger.debug(f"Releasing keys {keys_to_release} from window {hwnd}")
    release_keys(keys_to_release)


def release_directions(hwnd: int = None) -> None:
    if hwnd is None:
        hwnd = GetForegroundWindow()
    release_keys = []
    for key in ["left", "right"]:
        if (
            HIBYTE(
                GetAsyncKeyState(
                    _get_virtual_key(key, True, _keyboard_layout_handle(hwnd))
                )
            )
            != 0
        ):
            release_keys.append(key)
    if release_keys:
        logger.debug(f"Releasing keys {release_keys} from window {hwnd}")
    release_keys(release_keys)


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
        if isinstance(lst_inputs, str):  # Keyboard input
            SharedResources.keys_sent.add(lst_inputs)
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
        elif isinstance(lst_inputs, tuple) and lst_events is None:  # Mouse move input
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
        elif lst_inputs is None:  # Click events
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

        # Multiple inputs
        elif isinstance(lst_inputs, list) and isinstance(lst_events, list):
            assert len(lst_inputs) == len(lst_events)
            inputs = [
                _single_input_constructor(hwnd, i, e, as_unicode)
                for i, e in zip(lst_inputs, lst_events)
            ]
            for i in lst_inputs:
                SharedResources.keys_sent.add(i)
            num_inputs = len(inputs)
            array_class = Input * num_inputs
            array_pointer = ctypes.POINTER(array_class)
            input_array = array_class(*inputs)
            structures.append(
                (
                    wintypes.UINT(num_inputs),
                    array_pointer(input_array),
                    wintypes.INT(ctypes.sizeof(input_array[0])),
                )
            )

    return structures


async def focused_inputs(
    hwnd: int,
    inputs: list[tuple],
    delays: list[float],
    forced_key_releases: list[str] = None,
) -> int:
    """
    Sends the inputs to the active window.
    A small delay is added between each input.
    :param hwnd: handle to the window to send the inputs to.
    :param inputs: input structures to send.
    :param delays: delays between each input.
    :param forced_key_releases: If provided, these are sure to be released at the end,
    even if the task is cancelled.
    :return: Nbr of inputs successfully sent.
    """
    res = 0
    acquired = False
    try:
        acquired = await activate(hwnd)

        for i in range(len(inputs)):
            _send_input(inputs[i])
            res += 1
            await asyncio.sleep(delays[i])
        return res

    except asyncio.CancelledError as e:
        raise e

    except Exception as e:
        raise e

    finally:
        if forced_key_releases:
            keys_to_release = []
            for key in forced_key_releases:
                if (
                    HIBYTE(
                        GetAsyncKeyState(
                            _get_virtual_key(key, True, _keyboard_layout_handle(hwnd))
                        )
                    )
                    != 0
                ):
                    keys_to_release.append(key)
            release_keys(keys_to_release)
        if acquired:
            SharedResources.focus_lock.release()


def get_held_movement_keys(hwnd: int) -> list[str]:
    """
    Returns a list of the currently held movement keys.
    :param hwnd:
    :return:
    """
    return [
        key
        for key in OPPOSITES
        if HIBYTE(
            GetAsyncKeyState(
                _get_virtual_key(key, False, _keyboard_layout_handle(hwnd))
            )
        )
        != 0
    ]


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


def release_keys(keys: list[str], handle: int = None) -> None:
    """
    Releases the given keys.
    :param keys: Keys to release.
    :param handle: Handle to the window to release the keys.
    :return: Input structure to release the given keys.
    """
    if handle is None:
        handle = GetForegroundWindow()
    if keys:
        events: list[Literal] = ["keyup"] * len(keys)
        inputs = input_constructor(handle, [keys], [events])
        if inputs:
            _send_input(inputs[0])
