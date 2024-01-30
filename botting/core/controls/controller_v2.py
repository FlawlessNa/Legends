"""
Controller module for the game.
Contains all high-level functions necessary for interacting with the game.
"""
import asyncio
import functools
import logging
import numpy as np
import pytweening
import random
import win32api
import win32con
import win32gui
from typing import Literal

from botting.utilities import config_reader, randomize_params
from .inputs import focused_input, non_focused_input, focused_mouse_input
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
    central_delay: float = 0.033,
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
                yield random.uniform(0.95, 1.05) * delay

        delay_gen = _random_delay(central_delay)

        keys: list[list[str]] = [[direction]]
        events: list[list[Literal["keydown", "keyup"]]] = [["keydown"]]
        delays: list[float] = [next(delay_gen)]
        release_keys: list[str] = [direction]

        if secondary_direction:
            # Both keys pressed simultaneously in this case, so contained in same structure
            keys[0].append(secondary_direction)
            events[0].append("keydown")
            release_keys.append(secondary_direction)

        if jump:
            # Jump has a delay after primary+optional secondary direction
            keys.append([key_binds(ign)["jump"]])
            events.append(["keydown"])
            delays.append(next(delay_gen))
            release_keys.append(key_binds(ign)["jump"])

        if secondary_key_press:
            # Secondary key has a delay after primary+optional jump
            if tertiary_key_press:
                # Tertiary key is always sent simultaneously with secondary key
                keys.append([secondary_key_press, tertiary_key_press])
                events.append(["keydown", "keydown"])
                release_keys.extend([secondary_key_press, tertiary_key_press])
            else:
                keys.append([secondary_key_press])
                events.append(["keydown"])
                release_keys.append(secondary_key_press)
            delays.append(next(delay_gen))

        if automatic_repeat:
            _repeat_inputs(keys, events, delays, duration, central_delay, delay_gen)
        else:
            # Here delay between a keydown and keyup is twice the central (approx)
            num_repeats = int(
                (duration - sum(delays)) // jump_interval
            )  # or secondary_key_interval
            repeat_events = ["keydown", "keyup"]

            if tertiary_key_press:
                repeat_keys = [secondary_key_press, tertiary_key_press]
            elif secondary_key_press and jump:
                repeat_keys = [[key_binds(ign)["jump"]], [secondary_key_press]]
            elif secondary_key_press:
                repeat_keys = [secondary_key_press]
            elif jump:
                repeat_keys = [key_binds(ign)["jump"]]
            else:
                raise ValueError("Invalid combination of inputs.")
    except Exception as e:
        print('direction', direction)
        print('secondary_direction', secondary_direction)
        print('duration', duration)
        print('jump', jump)
        print('jump_interval', jump_interval)
        print('secondary_key_press', secondary_key_press)
        print('secondary_key_interval', secondary_key_interval)
        print('tertiary_key_press', tertiary_key_press)
        print('central_delay', central_delay)
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
    # TODO - Test this with FJ once available, or with attack + heal

    # Single + Jump interval + Second interval (No ARF, delay between jump & second)
    # TODO - Test this with FJ once available, or with attack + heal

    # Single + Secondary direction + Jump Hold + Second Key Hold (ARF - Second Key, delay between jump keydown and second keydown)
    # TODO - Test this with FJ once available

    # Single + Secondary direction + Jump interval + Second interval (No ARF, delay between jump & second)
    # TODO - Test this with FJ once available

    # Single + Second Key interval + Third Key interval (No ARF - 2nd/3rd simultaneous) (Strictly for telecasting)
    # TODO - test by telecasting

    inputs = _input_constructor()
    keys_to_release = _get_failsafe_keys(inputs)
    await _move(inputs, keys_to_release)


def _repeat_inputs(keys, events, delays, duration, central_delay, delay_gen):
    """
    Repeats the inputs for the given duration.
    """
    delays.append(0.5)  # The first automatic repeat is always about 0.5 s later
    upper_bound = int((duration - sum(delays)) // central_delay)
    assert upper_bound > 0
    repeated_key = keys[-1][-1]
    keys.extend([[repeated_key]] * upper_bound)
    events.extend([["keydown"]] * upper_bound)
    delays.extend([next(delay_gen)] * (upper_bound - 1))


@SharedResources.requires_focus
async def _move(
    inputs,
    keys_to_release,
) -> None:
    try:
        await _send_inputs(inputs)
    finally:
        _release(keys_to_release)
