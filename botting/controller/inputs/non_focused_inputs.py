"""
Low-level module that handles sending inputs to any window through PostMessage().
"""

import asyncio
import logging
from ctypes import wintypes
from typing import TypedDict, Unpack

import win32con

from .inputs_helpers import (
    _EXPORTED_FUNCTIONS,
    EXTENDED_KEYS,
    MAPVK_VK_TO_VSC_EX,
    _get_virtual_key,
    _keyboard_layout_handle,
)

SYS_KEYS = ["alt", "alt_right", "F10"]
logger = logging.getLogger(__name__)

PostMessageTuple = tuple[wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class LowParamKwargs(TypedDict, total=False):
    scan_code: int | None
    repeat_count: int
    previous_key_state: int | None
    context_code: int | None


async def non_focused_input(
    messages: list[PostMessageTuple],
    delays: list[float],
) -> None:
    for i, msg in enumerate(messages):
        _post_message(msg)
        await asyncio.sleep(delays[i])


def _post_message(
    msg: PostMessageTuple,
) -> None:
    failure_count = 0
    while not _EXPORTED_FUNCTIONS["PostMessageW"](*msg):
        logger.error("Failed to post message %s", msg)
        failure_count += 1
        if failure_count > 10:
            logger.critical(
                "Unable to post the message %s to the window %s", msg, msg[0]
            )
            raise RuntimeError(f"Failed to post message {msg} after 10 attempts.")


def message_constructor(
    hwnd: int,
    keys: list[str],
    messages: list[int],
    **kwargs: Unpack[LowParamKwargs],
) -> list[PostMessageTuple]:
    """
    Constructs the input array that will be sent to the window through PostMessage().
    :param hwnd: Handle to the window to send the message to.
    :param keys: List of string representation of the key(s) to be pressed.
    :param messages: Type of message to be sent, as the `win32con.WM_*`
     constants - plain ints, which is what `_single_message_constructor`
     takes.
     Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_CHAR.
     If it is a list, it must be the same length as the keys list.
    :param kwargs: Additional arguments to be passed to _low_param_constructor method.
    :return: list[tuples].
     Each tuple contains all necessary argument to be passed to PostMessage.
    """
    return_val: list[
        tuple[wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    ] = []
    assert isinstance(keys, list), "Keys must be a list."
    assert isinstance(messages, list), "Messages must be a list."
    assert len(keys) == len(messages), (
        "Msg and keys must have the same length when they are provided as lists."
    )
    for key, msg in zip(keys, messages):
        return_val.append(_single_message_constructor(hwnd, key, int(msg), **kwargs))
    return return_val


def _single_message_constructor(
    hwnd: int,
    key: str,
    message: int,
    **kwargs: Unpack[LowParamKwargs],
) -> PostMessageTuple:
    """
    Constructs the appropriate inputs that will be sent to the window associated with the
     provided handle through PostMessage(...).
     Delay is passed to allow for a different randomized value between each message.
    :param hwnd: Handle to the window to send the message to.
    :param key: String representation of the key to be pressed.
    :param message: Type of message to be sent.
     Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_CHAR.
    :param delay: Cooldown between each call of PostMessage(...). Will be randomized.
    :param kwargs: Arguments to be passed to the _low_param_constructor method.
    :return: list[tuples, float].
     The tuple contains all necessary argument to be passed to PostMessage.
     The float is the delay between each call of PostMessage.
    """

    if key in SYS_KEYS:
        message = win32con.WM_SYSKEYDOWN if message == win32con.WM_KEYDOWN else message
        message = win32con.WM_SYSKEYUP if message == win32con.WM_KEYUP else message

    extended_key = int(key in EXTENDED_KEYS)
    vk_key = _get_virtual_key(
        key,
        message == win32con.WM_CHAR,
        _keyboard_layout_handle(hwnd),
    )
    l_params = _low_param_constructor(
        hwnd, key=vk_key, command=message, extended_key=extended_key, **kwargs
    )
    return (
        wintypes.HWND(hwnd),
        wintypes.UINT(message),
        wintypes.WPARAM(vk_key),
        l_params,
    )


def _low_param_constructor(
    hwnd: int,
    key: int,
    command: int,
    extended_key: int,
    scan_code: int | None = None,
    repeat_count: int = 1,
    previous_key_state: int | None = None,
    context_code: int | None = None,
) -> wintypes.LPARAM:
    """
    Creates the LPARAM argument for the PostMessage function.
    :param hwnd: Handle to the window to send the message to.
    :param key: Key that will be sent through PostMessage
    :param command: Type of message to be sent.
     Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP.
    :param extended_key: Whether the key being press is part of the extended keys.
    :param scan_code: The scan code associated with the key.
     If None, it will be determined automatically.
    :param repeat_count: Number of times the key will be pressed.
     Default is 1. NOTE - Anything else won't work for now.
     This may be due to how the game handles these messages.
    :param previous_key_state: 1 to simulate that the key is down
     while the key is pressed. 0 otherwise.
    :param context_code: 1 to simulate that the ALT key is down while the key is
     pressed OR if the key to press is the ALT key. 0 otherwise.
    :return: LPARAM argument for the PostMessage function.
    """
    assert command in [
        win32con.WM_KEYDOWN,
        win32con.WM_KEYUP,
        win32con.WM_SYSKEYDOWN,
        win32con.WM_SYSKEYUP,
        win32con.WM_CHAR,
    ], f"Command {command} is not supported"
    assert repeat_count < 2**16

    if scan_code is None:
        scan_code = int(
            _EXPORTED_FUNCTIONS["MapVirtualKeyExW"](
                key, MAPVK_VK_TO_VSC_EX, _keyboard_layout_handle(hwnd)
            )
        )

    # Handle the context code and correct command code if necessary
    if context_code is None:
        # Note: Per online documentation, it should be if command in
        # [win32con.WM_SYSKEYDOWN, win32con.WM_SYSKEYUP],
        # but this is inconsistent with what Spy++ observes.
        context_code = (
            1 if command == win32con.WM_SYSKEYDOWN and key == win32con.VK_MENU else 0
        )

    # Use SYS KEYDOWN/SYS KEYUP if the key is the ALT key or if a different key
    # is being pressed while the ALT key is simulated to be down.
    if context_code == 1 or key == win32con.VK_MENU or key == win32con.VK_F10:
        if command == win32con.WM_KEYDOWN:
            command = win32con.WM_SYSKEYDOWN
        elif command == win32con.WM_KEYUP:
            command = win32con.WM_SYSKEYUP

    # Handle the previous key state flag
    if previous_key_state is None:
        previous_key_state = (
            1 if command in [win32con.WM_KEYUP, win32con.WM_SYSKEYUP] else 0
        )

    # Handle the transition flag. Always 0 for key down, 1 for key up.
    transition_state = (
        0 if command in [win32con.WM_KEYDOWN, win32con.WM_SYSKEYDOWN] else 1
    )

    return wintypes.LPARAM(
        repeat_count
        | (scan_code << 16)
        | (extended_key << 24)
        | (context_code << 29)
        | (previous_key_state << 30)
        | (transition_state << 31)
    )
