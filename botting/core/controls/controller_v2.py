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
    **kwargs
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

    Notes:
    If jump + secondary_key_press are present, both must have same interval
        (or be held down).
    If tertiary_key_press is provided, then secondary_direction and jump must be blank.

    Constructs the input structures outside the Focus Lock.
    Once determined, sends the input into the function that requires the Lock and which
    is solely responsible for sending the inputs to the appropriate game window.
    """
    assert direction in ["up", "down", "left", "right"]
    assert secondary_direction in [None, "up", "down", "left", "right"]
    assert jump_interval >= 0
    assert secondary_key_interval >= 0
    if jump and secondary_key_press:
        assert jump_interval == secondary_key_interval
    if tertiary_key_press:
        assert not secondary_direction and not jump

    keys = [direction]
    events: list[Literal["keydown", "keyup"]] = ["keydown"]

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


@SharedResources.requires_focus
async def _move(
    inputs,
    keys_to_release,
) -> None:
    try:
        await _send_inputs(inputs)
    finally:
        _release(keys_to_release)
