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
    full_input_constructor,
    full_input_mouse_constructor,
    message_constructor,
    repeat_inputs,
    move_params_validator,
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
    delay: float = 0.033 - time.get_clock_info("monotonic").resolution,
    **kwargs,
) -> None:
    """
    :param handle: Window handle to the process.
    :param key: String representation of the key to be pressed.
    :param silenced: Whether to activate the window before pressing the key.
     If True, the key is sent through PostMessage(...) instead of SendInput(...).
    :param down_or_up: Whether to send a keydown-only or keyup-only event.
     If None, both are sent.
    :param delay: Delay between the keydown and keyup events.
    :return: None
    """
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
            handle, [key] * 2, [win32con.WM_KEYDOWN, win32con.WM_KEYUP], **kwargs
        )
        delays = [random.uniform(0.95, 1.05) * delay for _ in range(2)]
        await non_focused_input(inputs, delays)

    else:
        inputs = []
        keys_to_release = None
        if down_or_up in ["keydown", None]:
            keys = [[key]]
            events = [["keydown"]]
            inputs = full_input_constructor(handle, keys, events)
        if down_or_up in ["keyup", None]:
            keys_to_release = full_input_constructor(handle, [[key]], [["keyup"]])[0]

        delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(inputs))]
        await focused_inputs(handle, inputs, delays, keys_to_release=keys_to_release)


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

        if delay == 0:
            message = [[char for char in list(message) for _ in range(2)]]
            events: list[list[Literal["keyup", "keydown"] | str]] = [
                ["keydown", "keyup"] * (len(message[0]) // 2)
            ]
            delays = [0]
        else:
            message = [[char] for char in list(message) for _ in range(2)]
            events = [["keydown"], ["keyup"]] * (len(message) // 2)
            delays = [random.uniform(0.95, 1.05) * delay for _ in range(len(message))]

        inputs = full_input_constructor(handle, message, events, as_unicode=True)
        await asyncio.shield(focused_inputs(handle, inputs, delays, None))


async def move(
    handle: int,
    ign: str,
    direction: Literal["up", "down", "left", "right"],
    duration: float,
    secondary_direction: Literal["up", "down", "left", "right"] = None,
    jump: bool = False,
    jump_interval: float = 0.0,
    secondary_key_press: str = None,
    secondary_key_interval: float = 0.0,
    combine_jump_secondary: bool = None,
    tertiary_key_press: str = None,
    central_delay: float = 0.033 - time.get_clock_info("monotonic").resolution,
) -> None:
    """
    :param handle: Handle to the game window.
    :param ign: In-game character name.
    :param direction: Direction to move in.
    :param duration: Duration of the movement.
    :param secondary_direction: Optional. Secondary direction to move in.
        Use to climb up/down ladders and enter portals, or jump down platforms.
    :param jump: Optional. Whether to jump.
        Use in combination with secondary_direction to jump into ropes or jump
        down a platform.
    :param jump_interval: Optional. Interval between each jump. If 0, hold the jump key.
    :param secondary_key_press: Optional. Secondary key to press.
        Use for certain movement skills (Teleport, Flash Jump, Rush, etc.).
    :param secondary_key_interval: Optional. Interval between each press of the secondary
        key. If 0, hold the secondary key.
    :param combine_jump_secondary: Optional. Whether to combine the jump and secondary
        key into a single structure (can be used to jump attack).
    :param tertiary_key_press: Optional. Tertiary key to press.
        Strictly used for telecasting. Cannot be held down, and will always be sent
        simultaneously with secondary press(es).
    :param central_delay: Delay between standard automatic repeat feature.
        The actual delay from real human input, as observed with Spy++, is ~0.033s.
        Using asyncio.sleep(), there is uncertainty based on clock resolution, so we
        adjust for that.

    Notes:
    If jump + secondary_key_press are present, both must have same interval > 0.
    If tertiary_key_press is provided, then secondary_direction and jump must be blank.
    In this case, secondary_key_press must be provided with secondary_key_interval

    Constructs the input structures outside the Focus Lock.
    Once determined, sends the input into the function that requires the Lock and which
    is solely responsible for sending the inputs to the appropriate game window.
    """
    try:
        move_params_validator(
            direction,
            secondary_direction,
            duration,
            central_delay,
            jump,
            jump_interval,
            secondary_key_press,
            secondary_key_interval,
            tertiary_key_press,
            combine_jump_secondary,
        )

        automatic_repeat = True
        if jump and jump_interval > 0:
            automatic_repeat = False
        if secondary_key_press and secondary_key_interval > 0:
            automatic_repeat = False
        if tertiary_key_press:
            automatic_repeat = False

        def _random_delay(delay: float):
            while True:
                new_val = random.uniform(0.95, 1.05)
                yield new_val * delay

        delay_gen = _random_delay(central_delay)

        keys: list[list[Literal["up", "down", "left", "right"] | str]] = [[direction]]
        release_keys: list[Literal["up", "down", "left", "right"] | str] = [direction]
        events: list[list[Literal["keydown", "keyup"]]] = [["keydown"]]
        if automatic_repeat:
            delays: list[float] = [0.5]  # First delay before automatic repeat
        elif combine_jump_secondary and jump and secondary_key_press:
            # The only case where we have to combine jump and secondary key
            delays: list[float] = [0.25, next(delay_gen) * 2]
        else:
            delays: list[float] = [next(delay_gen) * 2]  # Delay b/w keyup and keydown

        if automatic_repeat:
            if secondary_direction is not None and jump:
                keys[0].extend([secondary_direction, key_binds(ign)["jump"]])
                events[0].extend(["keydown", "keydown"])
                release_keys.extend([secondary_direction, key_binds(ign)["jump"]])
            elif jump:
                keys[0].append(key_binds(ign)["jump"])
                events[0].append("keydown")
                release_keys.append(key_binds(ign)["jump"])
            elif secondary_direction:
                keys[0].append(secondary_direction)
                events[0].append("keydown")
                release_keys.append(secondary_direction)
            elif secondary_key_press:
                keys[0].append(secondary_key_press)
                events[0].append("keydown")
                release_keys.append(secondary_key_press)
            elif not secondary_key_press and not secondary_direction and not jump:
                pass
            else:
                raise ValueError("Invalid combination of inputs.")

            repeat_inputs(keys, events, delays, duration, central_delay, delay_gen)

        else:
            num_triggers = int(
                (duration - sum(delays)) // max(jump_interval, secondary_key_interval)
            )

            if secondary_direction is not None and jump and secondary_key_press:
                breakpoint()

            elif secondary_direction is not None and jump:
                keys[0].extend([secondary_direction, key_binds(ign)["jump"]])
                events[0].extend(["keydown", "keydown"])
                release_keys.extend([secondary_direction, key_binds(ign)["jump"]])
                keys.append([key_binds(ign)["jump"]])
                events.append(["keyup"])
                delays.append(jump_interval)

                for _ in range(num_triggers):
                    keys.extend([[key_binds(ign)["jump"]], [key_binds(ign)["jump"]]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([2 * next(delay_gen), jump_interval])

            elif jump and secondary_key_press and combine_jump_secondary:
                keys.append([key_binds(ign)["jump"], secondary_key_press])
                events.append(["keydown", "keydown"])
                release_keys.extend([key_binds(ign)["jump"], secondary_key_press])
                keys.append([key_binds(ign)["jump"], secondary_key_press])
                events.append(["keyup", "keyup"])
                delays.append(jump_interval)

                for _ in range(num_triggers):
                    keys.extend(
                        [
                            [key_binds(ign)["jump"], secondary_key_press],
                            [key_binds(ign)["jump"], secondary_key_press],
                        ]
                    )
                    events.extend([["keydown", "keydown"], ["keyup", "keyup"]])
                    delays.extend([2 * next(delay_gen), jump_interval])

            elif jump and secondary_key_press:
                keys[0].append(key_binds(ign)["jump"])
                events[0].append("keydown")
                release_keys.extend([key_binds(ign)["jump"], secondary_key_press])
                keys.append([key_binds(ign)["jump"]])
                events.append(["keyup"])
                delays.append(jump_interval / 2)
                keys.extend([[secondary_key_press], [secondary_key_press]])
                events.extend([["keydown"], ["keyup"]])
                delays.extend([2 * next(delay_gen), secondary_key_interval / 2])

                for _ in range(num_triggers):
                    keys.extend([[key_binds(ign)["jump"]], [key_binds(ign)["jump"]]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([2 * next(delay_gen), jump_interval / 2])
                    keys.extend([[secondary_key_press], [secondary_key_press]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([2 * next(delay_gen), secondary_key_interval / 2])

            elif jump:
                keys[0].append(key_binds(ign)["jump"])
                events[0].append("keydown")
                release_keys.append(key_binds(ign)["jump"])
                keys.append([key_binds(ign)["jump"]])
                events.append(["keyup"])
                delays.append(jump_interval)

                for _ in range(num_triggers):
                    keys.extend([[key_binds(ign)["jump"]], [key_binds(ign)["jump"]]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([2 * next(delay_gen), jump_interval])

            elif tertiary_key_press:
                keys[0].extend([secondary_key_press, tertiary_key_press])
                events[0].extend(["keydown", "keydown"])
                release_keys.extend([secondary_key_press, tertiary_key_press])
                keys.append([secondary_key_press, tertiary_key_press])
                events.append(["keyup", "keyup"])
                delays.append(secondary_key_interval)

                for _ in range(num_triggers):
                    keys.extend(
                        [
                            [secondary_key_press, tertiary_key_press],
                            [secondary_key_press, tertiary_key_press],
                        ]
                    )
                    events.extend([["keydown", "keydown"], ["keyup", "keyup"]])
                    delays.extend([2 * next(delay_gen), secondary_key_interval])

            elif secondary_key_press:
                keys[0].append(secondary_key_press)
                events[0].append("keydown")
                release_keys.append(secondary_key_press)
                keys.append([secondary_key_press])
                events.append(["keyup"])
                delays.append(secondary_key_interval)

                for _ in range(num_triggers):
                    keys.extend([[secondary_key_press], [secondary_key_press]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([2 * next(delay_gen), secondary_key_interval])
            else:
                raise ValueError("Invalid combination of inputs.")

        release_events: list[list[Literal["keyup", "keydown"] | str]] = [
            ["keyup"] * len(release_keys)
        ]
        release_keys: list[list[Literal["up", "down", "left", "right"] | str]] = [
            release_keys
        ]

    except Exception as e:
        print("direction", direction)
        print("secondary_direction", secondary_direction)
        print("duration", duration)
        print("jump", jump)
        print("jump_interval", jump_interval)
        print("secondary_key_press", secondary_key_press)
        print("secondary_key_interval", secondary_key_interval)
        print("tertiary_key_press", tertiary_key_press)
        print("central_delay", central_delay)
        raise e

    assert len(keys) == len(events) == len(delays)
    inputs = full_input_constructor(handle, keys, events)
    release_inputs = full_input_constructor(handle, release_keys, release_events)
    assert len(release_inputs) == 1
    try:
        await asyncio.wait_for(
            focused_inputs(handle, inputs, delays, release_inputs[0]), duration
        )
    except asyncio.TimeoutError:
        pass


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

    inputs = full_input_mouse_constructor(x, y, [None], [None])

    await focused_inputs(handle, inputs, delays, None)


async def click(
    handle: int,
    down_or_up: Literal["click", "down", "up"] = "click",
    nbr_times: int = 1,
    delay: float = 0.1,
) -> None:
    """
    :param handle: Window handle to the process.
    :param down_or_up: Whether to click, press down or release the mouse button.
    :param nbr_times: Number of times to click.
    :param delay: Delay between each click.
    :return:
    """
    events = [down_or_up] * nbr_times
    delays = [random.uniform(0.95, 1.05) * delay for _ in range(nbr_times)]
    inputs = full_input_mouse_constructor([None], [None], events, [None])
    await focused_inputs(handle, inputs, delays, None)


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
