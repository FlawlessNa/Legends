"""
Controller module for the game.
Contains all high-level functions necessary for interacting with the game.
"""
import asyncio
import functools
import logging
import time
import numpy as np
import pytweening
import random
import win32api
import win32con
import win32gui
from typing import Literal

from botting.utilities import config_reader, randomize_params
from .inputs import (
    focused_inputs,
    non_focused_input,
    message_constructor,
    DELAY,
    input_constructor,
    release_all,
)

logger = logging.getLogger(__name__)
WIDTH, HEIGHT = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)


def get_refresh_rate() -> int:
    """
    Retrieves the refresh rate of the monitor.
    :return: Refresh rate in Hz.
    """
    return int(win32api.EnumDisplaySettings().DisplayFrequency)


REFRESH_RATE = get_refresh_rate()


@functools.lru_cache
def key_binds(ign: str) -> dict[str, str]:
    """
    Retrieves the key bindings for the associated character from the keybindings
     config file.
    The configs cannot be changed while the bot is running.
    In-game key binds should therefore not be changed either.
    """
    temp = {k: eval(v) for k, v in dict(config_reader("keybindings", f"{ign}")).items()}
    final = {}
    for val in temp.values():
        final.update(val)
    logger.debug(f"Key bindings successfully retrieved for {ign}.")
    return final


async def press(
    handle: int,
    key: str,
    silenced: bool = False,
    down_or_up: Literal["keydown", "keyup"] | None = None,
    nbr_times: int = 1,
    delay: float = DELAY,
    **kwargs,
) -> None:
    """
    :param handle: Window handle to the process.
    :param key: String representation of the key to be pressed.
    :param silenced: Whether to activate the window before pressing the key.
     If True, the key is sent through PostMessage(...) instead of SendInput(...).
    :param down_or_up: Whether to send a keydown-only or keyup-only event.
     If None, both are sent.
    :param nbr_times: Number of times to press the key.
    :param delay: Delay between the keydown and keyup events.
    :return: None
    """
    if down_or_up != "keyup":
        assert key not in [
            "up",
            "down",
            "left",
            "right",
        ], "Use the move function to move the character."
    if down_or_up is not None:
        assert down_or_up in ["keydown", "keyup"]
        assert (
            not silenced
        ), "Cannot send a keydown or keyup (as stand-alone) event when silenced=True."

    if silenced:
        inputs = message_constructor(
            handle,
            [key] * 2 * nbr_times,
            [win32con.WM_KEYDOWN, win32con.WM_KEYUP] * nbr_times,
            **kwargs,
        )
        delays = [random.uniform(0.95, 1.05) * delay for _ in range(2 * nbr_times)]
        await non_focused_input(inputs, delays)

    else:
        inputs = []
        keys = []
        events = []
        release = None
        if down_or_up in ["keydown", None]:
            keys = [[key]] * nbr_times
            events: list[Literal | list] = [["keydown"]] * nbr_times
            inputs = input_constructor(handle, keys, events)
        if down_or_up in ["keyup", None]:
            release = [key]
            keys.append([key])
            events.append(["keyup"])

        delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(inputs))]
        await focused_inputs(handle, inputs, delays, release)


async def write(
    handle: int,
    message: str,
    silenced: bool = True,
    delay: float = 0.033 - time.get_clock_info("monotonic").resolution,
) -> None:
    """
    Write a message in the specified window.

    Notes:
    When silenced=True, We use the WM_CHAR command to allow for differentiation
     of lower and upper case letters. This by-passes the KEYDOWN/KEYUP commands.
    Therefore, this creates "non-human" inputs sent to the window and as such,
     should only be used to actually write stuff in the chat and nothing else
     (anti-detection prevention).
    When silenced=False, the SendInput function creates VK_PACKETS with are sent to
     the window to replicate any custom chars. This also creates "non-human" behavior.

    :param handle: Window handle to the process.
    :param message: Actual message to be typed.
    :param silenced: Whether to write input to the active window or not.
     If True, the key is sent through PostMessage(...) instead of SendInput(...).
    :param delay: Delay between each character.
        If 0, the entire message is sent at once.
    :return: None
    Note:
        When silenced=False, the focused_inputs is shielded from cancellation, such
        that the entire message is written before the lock releases.
    """
    release_all(handle)
    if silenced:
        logger.info(f"Writing message {message} in window {handle} silently.")
        inputs = message_constructor(
            handle,
            list(message),
            [win32con.WM_CHAR] * len(message),
        )
        delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(message))]
        await non_focused_input(inputs, delays)

    else:
        logger.info(f"Writing message {message} in window {handle} LOUDLY.")
        release_keys = list(set(message))

        if delay == 0:
            message = [[char for char in list(message) for _ in range(2)]]
            events: list[list[Literal]] = [
                ["keydown", "keyup"] * (len(message[0]) // 2)
            ]
            delays = [0]
        else:
            message = [[char] for char in list(message) for _ in range(2)]
            events = [["keydown"], ["keyup"]] * (len(message) // 2)
            delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(message))]

        inputs = input_constructor(handle, message, events, as_unicode=True)
        await asyncio.shield(focused_inputs(handle, inputs, delays, release_keys))


@randomize_params("total_duration")
async def mouse_move(
    handle: int,
    target: tuple[int | float, int | float],
    total_duration: float = 0.5,
) -> None:
    """
    Calculates the mouse movement path and sends the inputs to the window.
    A random tweening function is chosen, which dictates the shape of the trajectory.
    :param handle: Window handle to the process.
    :param target: Target position of the mouse.
    :param total_duration: Duration of the movement. If 0, the mouse is moved instantly.
    """
    tween = random.choice(
        [
            pytweening.easeInQuad,
            pytweening.easeOutQuad,
            pytweening.easeInOutQuad,
            pytweening.easeInCubic,
            pytweening.easeOutCubic,
            pytweening.easeInOutCubic,
            pytweening.easeInQuart,
            pytweening.easeOutQuart,
            pytweening.easeInOutQuart,
            pytweening.easeInQuint,
            pytweening.easeOutQuint,
            pytweening.easeInOutQuint,
            pytweening.easeInSine,
            pytweening.easeOutSine,
            pytweening.easeInOutSine,
            pytweening.easeInExpo,
            pytweening.easeOutExpo,
            pytweening.easeInOutExpo,
            pytweening.easeInCirc,
            pytweening.easeOutCirc,
            pytweening.easeInOutCirc,
            pytweening.easeInElastic,
            pytweening.easeOutElastic,
            pytweening.easeInOutElastic,
            pytweening.easeInBack,
            pytweening.easeOutBack,
            pytweening.easeInOutBack,
            pytweening.easeInBounce,
            pytweening.easeOutBounce,
            pytweening.easeInOutBounce,
        ]
    )

    window_rect = win32gui.GetWindowRect(handle)
    x0, y0 = win32api.GetCursorPos()
    x1 = target[0] + window_rect[0]
    y1 = target[1] + window_rect[1]

    if total_duration == 0:
        x, y = [int(x1 * 65536 // WIDTH)], [int(y1 * 65536 // HEIGHT)]
        delays = [0]

    else:
        step_duration: float = max(1 / REFRESH_RATE, 0.03)
        num_steps = int(total_duration / step_duration)
        rng = np.linspace(0, 1, num_steps)
        trajectory = [pytweening.getPointOnLine(x0, y0, x1, y1, tween(t)) for t in rng]
        x, y = zip(*trajectory)
        x = [int(i * 65536 // WIDTH) for i in x]
        y = [int(i * 65536 // HEIGHT) for i in y]
        delays = [step_duration] * len(x)

    inputs = input_constructor(handle, list(zip(x, y)), [None] * len(x))
    await focused_inputs(handle, inputs, delays)


async def click(
    handle: int,
    down_or_up: Literal["click", "mousedown", "mouseup"] = "click",
    nbr_times: int = 1,
    delay: float = DELAY,
) -> int:
    """
    :param handle: Window handle to the process.
    :param down_or_up: Whether to click, press down or release the mouse button.
    :param nbr_times: Number of times to click.
    :param delay: Delay between each click.
    :return: Nbr of times the click was successful.
    """
    if down_or_up == "click":
        events = ["mousedown", "mouseup"] * nbr_times
    else:
        events = [down_or_up] * nbr_times
    delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(events))]
    inputs = input_constructor(handle, [None] * len(events), events)
    return await focused_inputs(handle, inputs, delays)


def get_mouse_pos(handle: int) -> tuple[int, int]:
    """
    Returns the position of the cursor inside the window, if it is inside the window.
    Otherwise, returns None.
    :param handle:
    :return:
    """
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    x, y = win32api.GetCursorPos()
    if left <= x <= right and top <= y <= bottom:
        return x - left, y - top
