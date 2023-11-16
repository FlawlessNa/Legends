"""
Low-level module that handles inputs sent to a window through either PostMessage(...) or SendInput(...) functions.
"""
import asyncio
import logging
import win32con
import win32gui

from ctypes import wintypes
from typing import Literal
from win32api import GetKeyState

from .non_focused_inputs import _message_constructor, _post_messages
from .focused_inputs import _input_array_constructor, _send_inputs
from .inputs_helpers import _EXPORTED_FUNCTIONS
from botting.utilities import randomize_params

logger = logging.getLogger(__name__)


if GetKeyState(win32con.VK_NUMLOCK) != 0:
    logger.info("NumLock is on. Turning it off.")
    num_lock_inputs = _input_array_constructor(
        hwnd=win32gui.GetForegroundWindow(),
        keys=["num_lock", "num_lock"],
        events=["keydown", "keyup"],
        enforce_delay=False,
    )[0][0]
    _EXPORTED_FUNCTIONS["SendInput"](*num_lock_inputs)


@randomize_params("cooldown")
async def non_focused_input(
    hwnd: int,
    keys: str | list[str],
    messages: wintypes.UINT | list[wintypes.UINT],
    delay: float = 0.033,
    cooldown: float = 0.1,
    **kwargs
) -> None:
    """
    Constructs the input array of structures to be sent to the window associated the provided handle. Send that input through PostMessage.
    Note: While this function is broken down in two components, there's no real gain in doing so. It is merely for consistency with the _focused_input() version.
    :param hwnd: Handle to the window to send the message to.
    :param keys: String representation of the key(s) to be pressed.
    :param messages: Type of message to be sent. Currently supported: WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_CHAR. If it is a list, it must be the same length as the keys list.
    :param delay: Cooldown between each call of PostMessage(...). Default is 0.033 seconds.
    :param cooldown: Cooldown after all messages have been sent. Default is 0.1 seconds.
    :return: None
    """
    if isinstance(
        keys, str
    ):  # If only one key is provided, we convert it to a list to simplify the rest of the code. In such a case, we also set delay to 0.
        keys = [keys] * len(messages) if isinstance(messages, list) else [keys]
        delay = 0 if len(keys) == 1 else delay
    if not isinstance(messages, list):
        messages = [messages]

    items = _message_constructor(
        hwnd, keys=keys, messages=messages, delay=delay, **kwargs
    )
    await _post_messages(items, cooldown=cooldown)


@randomize_params("cooldown")
async def focused_input(
    hwnd: int,
    keys: str | list[str],
    event_type: Literal["keyup", "keydown"] | list[Literal["keyup", "keydown"]],
    enforce_delay: bool,
    as_unicode: bool = False,
    delay: float = 0.033,
    cooldown: float = 0.1,
) -> None:
    """
    Constructs the input array of structures to be sent to the window associated with this InputHandler instance. It then activates and sends the input to the window through SendInput.
    Note: This function is broken down to allow only the input construction to be made without using the Focus Lock. The Lock is therefore only used once everything is ready to be sent.
    :param hwnd: Handle to the window to send the message to.
    :param keys: String representation of the key(s) to be pressed.
    :param event_type: Type of event to be sent. Currently supported: keyup, keydown. If it is a list, it must be the same length as the keys list.
    :param enforce_delay: Whether to enforce a delay between each key press.
    :param as_unicode: Whether to send the keys as unicode characters. If True, the keys must be of length 1.
    :param delay: Delay between each call of SendInput(...). Default is 0.033 seconds.
    :param cooldown: Cooldown after all messages have been sent. Default is 0.1 seconds.
    :return: None
    """
    if isinstance(keys, str):
        keys = [keys] * len(event_type) if isinstance(event_type, list) else [keys]
    if not isinstance(event_type, list):
        event_type = [event_type]

    inputs = _input_array_constructor(
        hwnd,
        keys=keys,
        events=event_type,
        enforce_delay=enforce_delay,
        as_unicode=as_unicode,
        delay=delay,
    )
    await _send_inputs(hwnd, inputs)
    await asyncio.sleep(cooldown)  # The cooldown is not within _send_inputs as this would hold the focus lock during cooldown.
