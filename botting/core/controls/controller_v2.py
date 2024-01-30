"""
Controller module for the game.
Contains all high-level functions necessary for interacting with the game.
"""
import asyncio
import ctypes
import functools
import logging
import time

import numpy as np
import pytweening
import random
import win32api
import win32con
import win32gui
from ctypes import wintypes
from typing import Literal

from botting.utilities import config_reader, randomize_params
from .inputs import focused_input, non_focused_input, focused_mouse_input
from .inputs.focused_inputs_v2 import (
    activate,
    _full_input_constructor,
    Input,
    _EXPORTED_FUNCTIONS,
)
from .inputs.shared_resources import SharedResources

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
    tertiary_key_press: str = None,
    central_delay: float = 0.033 - time.get_clock_info("monotonic").resolution,
    **kwargs,
) -> None:
    """
    :param handle: Handle to the game window.
    :param ign: In-game character name.
    :param direction: Direction to move in.
    :param duration: Duration of the movement.
    :param secondary_direction: Optional. Secondary direction to move in.
        Use to climb up/down ladders and enter portals.
    :param jump: Optional. Whether to jump.
        Use in combination with secondary_direction to jump into ropes or jump
        down a platform.
    :param jump_interval: Optional. Interval between each jump. If 0, hold the jump key.
    :param secondary_key_press: Optional. Secondary key to press.
        Use for certain movement skills (Teleport, Flash Jump, Rush, etc.).
    :param secondary_key_interval: Optional. Interval between each press of the secondary
        key. If 0, hold the secondary key.
    :param tertiary_key_press: Optional. Tertiary key to press.
        Strictly used for telecasting. Cannot be held down, and will always be sent
        simultaneously with secondary press(es).
    :param central_delay: Delay between standard automatic repeat feature.
        The actual delay from real human input, as observed with Spy++, is ~0.033s.
        Using asyncio.sleep(), there is uncertainty based on clock resolution, so we
        adjust for that.

    Notes:
    If jump + secondary_key_press are present, both must have same interval
        (or be held down).
    If tertiary_key_press is provided, then secondary_direction and jump must be blank.
    In this case, secondary_key_press must be provided with secondary_key_interval

    Constructs the input structures outside the Focus Lock.
    Once determined, sends the input into the function that requires the Lock and which
    is solely responsible for sending the inputs to the appropriate game window.
    """
    try:
        assert direction in ["up", "down", "left", "right"]
        assert secondary_direction in [None, "up", "down", "left", "right"]
        assert duration > 0 and central_delay > 0
        assert jump_interval >= 0
        assert secondary_key_interval >= 0
        if jump and secondary_key_press:
            assert jump_interval == secondary_key_interval
        if tertiary_key_press:
            assert not secondary_direction and not jump
            assert secondary_key_press is not None
            assert secondary_key_interval > 0

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

        keys: list[list[str]] = [[direction]]
        events: list[list[Literal["keydown", "keyup"]]] = [["keydown"]]
        if automatic_repeat:
            delays: list[float] = [0.5]  # First delay before automatic repeat
        else:
            delays: list[float] = [next(delay_gen)]
        release_keys: list[str] = [direction]

        # Primary + Secondary direction always sent simultaneously
        # Jump + Secondary key always sent simultaneously
        # Secondary + Tertiary key always sent simultaneously

        if secondary_direction:
            # Both keys pressed simultaneously, so contain in same structure
            keys[0].append(secondary_direction)
            events[0].append("keydown")
            release_keys.append(secondary_direction)

        if jump and secondary_key_press:
            keys.append([key_binds(ign)["jump"], secondary_key_press])
            events.append(["keydown", "keydown"])
            release_keys.extend([key_binds(ign)["jump"], secondary_key_press])
            delays.insert(0, next(delay_gen))
        elif jump:
            # Jump has a delay after primary+optional secondary direction
            keys.append([key_binds(ign)["jump"]])
            events.append(["keydown"])
            release_keys.append(key_binds(ign)["jump"])
            delays.insert(0, next(delay_gen))

        elif secondary_key_press:
            # Secondary key has a delay after primary+optional jump
            if tertiary_key_press:
                # Tertiary key is always sent simultaneously with secondary key
                keys[0].extend([secondary_key_press, tertiary_key_press])
                events[0].extend(["keydown", "keydown"])
                release_keys.extend([secondary_key_press, tertiary_key_press])
            else:
                # Both keys pressed simultaneously, so contain in same structure
                keys[0].append(secondary_key_press)
                events[0].append("keydown")
                release_keys.append(secondary_key_press)

        release_events = [["keyup"] * len(release_keys)]
        release_keys: list[list[str | Literal]] = [release_keys]
        if automatic_repeat:
            _repeat_inputs(keys, events, delays, duration, central_delay, delay_gen)
        else:
            if secondary_key_press and jump:
                keys.append([key_binds(ign)["jump"], secondary_key_press])
                events.append(["keyup", "keyup"])
                delays[-1] = delays[-1] * 2  # Longer delay between keydown and keyup
                delays.append(jump_interval)
            elif secondary_key_press:
                keys.append([secondary_key_press])
                events.append(["keyup"])
                delays[-1] = delays[-1] * 2  # Longer delay between keydown and keyup
                delays.append(jump_interval)
            elif jump:
                keys.append([key_binds(ign)["jump"]])
                events.append(["keyup"])
                delays[-1] = delays[-1] * 2  # Longer delay between keydown and keyup
                delays.append(jump_interval)
            else:
                raise ValueError("Invalid combination of inputs.")

            # Here delay between a keydown and keyup is twice the central (approx)
            num_repeats = int(
                (duration - sum(delays)) // max(jump_interval, secondary_key_interval)
            )  # or secondary_key_interval

            for _ in range(num_repeats):
                if tertiary_key_press:
                    keys.append([secondary_key_press, tertiary_key_press])
                    events.append(["keydown", "keydown"])
                    # Longer delay between keydown and keyup
                    delays.append(next(delay_gen) * 2)
                    keys.append([secondary_key_press, tertiary_key_press])
                    events.append(["keyup", "keyup"])
                    delays.append(secondary_key_interval)

                elif secondary_key_press and jump:
                    keys.extend([[key_binds(ign)["jump"]], [key_binds(ign)["jump"]]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([next(delay_gen) * 2, next(delay_gen)])
                    keys.extend([[secondary_key_press], [secondary_key_press]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([next(delay_gen) * 2, jump_interval])

                elif secondary_key_press:
                    keys.extend([[secondary_key_press], [secondary_key_press]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([next(delay_gen) * 2, secondary_key_interval])
                elif jump:
                    keys.extend([[key_binds(ign)["jump"]], [key_binds(ign)["jump"]]])
                    events.extend([["keydown"], ["keyup"]])
                    delays.extend([next(delay_gen) * 2, jump_interval])

                else:
                    raise ValueError("Invalid combination of inputs.")

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

    # Single direction (ARF - direction)

    # Single + Secondary direction (ARF - secondary)

    # Single + Jump Hold (ARF - jump)

    # Single + Secondary + Jump Hold (ARF - jump)

    # Single + interval jump (No ARF - as soon as jump key pressed)

    # Single + Secondary + interval jump (No ARF - as soon as jump key pressed)

    # Single + Second Key Hold (ARF - Second key)

    # Single + Second Key interval (No ARF - as soon as Second key pressed)

    # Single + Jump Hold + Second Key Hold (ARF - Second Key)
    # TODO - Test this with FJ once available

    # Single + Jump interval + Second interval (No ARF, delay between jump & second)

    # Single + Secondary direction + Jump Hold + Second Key Hold (ARF - Second Key, delay between jump keydown and second keydown)
    # TODO - Test this with FJ once available

    # Single + Secondary direction + Jump interval + Second interval (No ARF, delay between jump & second)
    # TODO - Test this with FJ once available

    # Single + Second Key interval + Third Key interval (No ARF - 2nd/3rd simultaneous) (Strictly for telecasting)
    # TODO - test by telecasting

    assert len(keys) == len(events) == len(delays)
    inputs = _full_input_constructor(handle, keys, events)
    release_inputs = _full_input_constructor(handle, release_keys, release_events)
    assert len(release_inputs) == 1
    try:
        await asyncio.wait_for(
            _move(handle, inputs, delays, release_inputs[0]), duration
        )
    except asyncio.TimeoutError:
        pass


def _repeat_inputs(keys, events, delays, duration, central_delay, delay_gen):
    """
    Repeats the inputs for the given duration.
    """
    upper_bound = int((duration - sum(delays)) // central_delay)
    assert upper_bound > 0
    repeated_key = keys[-1][-1]
    keys.extend([[repeated_key]] * upper_bound)
    events.extend([["keydown"]] * upper_bound)
    delays_to_add = len(events) - len(delays)
    delays.extend([next(delay_gen) for _ in range(delays_to_add)])


@SharedResources.requires_focus
async def _move(
    hwnd: int,
    inputs: list[tuple],
    delays: list[float],
    keys_to_release: tuple,
) -> None:
    i = len(delays) - 1  # Just to make sure i always defined when finally is reached
    try:
        activate(hwnd)
        for i in range(len(inputs)):
            _send_inputs(inputs[i])
            await asyncio.sleep(delays[i])
    except Exception as e:
        raise e
    finally:
        time.sleep(min(delays))
        _send_inputs(keys_to_release)


def _send_inputs(structure: tuple) -> None:
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
