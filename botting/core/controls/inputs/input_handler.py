"""
Low-level module that handles inputs sent to a window through either
PostMessage(...) or SendInput(...) functions.
"""
import asyncio
import logging
import win32con
import win32gui

from ctypes import wintypes
from typing import Literal


from .focused_inputs import (
    _send_input,
    # _mouse_input_array_constructor,
)
from .inputs_helpers import _EXPORTED_FUNCTIONS
from botting.utilities import randomize_params

logger = logging.getLogger(__name__)


@randomize_params("cooldown")
async def focused_mouse_input(
    hwnd: int,
    x_trajectory: list[int] | None,
    y_trajectory: list[int] | None,
    events: list[Literal["click", "down", "up"]] | None,
    delay: float = 0.033,
    mouse_data: list[int] | None = None,
    cooldown: float = 0.1,
):
    """
    Constructs the input array of mouse structures to be sent to the window.
    Note: This function is broken down to allow only the input construction to be made
     without using the Focus Lock.
     The Lock is only used once everything is ready to be sent.
    :param hwnd: Handle to the window to send the mouse inputs to.
    :param x_trajectory: List of absolute X position of the mouse.
    :param y_trajectory: List of absolute Y position of the mouse.
    :param events: Type of Event to be sent. "click", "down", or "up".
    :param delay: Delay between each call of SendInput(...). Default is 0.033 seconds.
    :param mouse_data: Mouse game_data to be sent with the mouse event,
        should be 0 except for scrolling events.
    :param cooldown: Cooldown after all inputs are sent. Default is 0.1 seconds.
    :return: None
    """
    if not isinstance(x_trajectory, list):
        x_trajectory = [x_trajectory]

    if not isinstance(y_trajectory, list):
        y_trajectory = [y_trajectory]

    if not isinstance(events, list):
        events = [events] * len(x_trajectory)

    if mouse_data is None:
        mouse_data = [0] * len(events)

    inputs = _mouse_input_array_constructor(
        x_trajectory=x_trajectory,
        y_trajectory=y_trajectory,
        events=events,
        mouse_data=mouse_data,
        delay=delay,
    )
    await _send_input(hwnd, inputs)
    await asyncio.sleep(cooldown)
