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
    message_constructor,
    repeat_inputs,
    move_params_validator
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
    temp = {k: eval(v) for k, v in dict(
        config_reader("keybindings", f"{ign}")).items()
            }
    final = {}
    for val in temp.values():
        final.update(val)
    logger.debug(f"Key bindings successfully retrieved for {ign}.")
    return final


async def write(
    handle: int,
    message: str,
    silenced: bool = True,
    delay: float = 0.033 - time.get_clock_info("monotonic").resolution,
    **kwargs,
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
        inputs = message_constructor(handle,
                                     list(message),
                                     [win32con.WM_CHAR] * len(message),
                                     )
        delays = [
            random.uniform(0.95, 1.05) * delay for _ in range(len(message))
        ]
        await non_focused_input(
            inputs,
            delays
        )

    else:
        logger.info(f"Writing message {message} in window {handle} LOUDLY.")

        if delay == 0:
            message = [[char for char in list(message) for _ in range(2)]]
            events: list[
                list[Literal["keyup", "keydown"] | str]
            ] = [["keydown", "keyup"] * (len(message[0]) // 2)]
            delays = [0]
        else:
            message = [[char] for char in list(message) for _ in range(2)]
            events = [["keydown"], ["keyup"]] * (len(message) // 2)
            delays = [
                random.uniform(0.95, 1.05) * delay for _ in range(len(message))
            ]

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
            combine_jump_secondary
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
        release_keys = [direction]
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
                    keys.extend([[key_binds(ign)["jump"], secondary_key_press],
                                 [key_binds(ign)["jump"], secondary_key_press]])
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
                    keys.extend([[secondary_key_press, tertiary_key_press],
                                 [secondary_key_press, tertiary_key_press]])
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

        release_events: list[
            list[Literal["keyup", "keydown"] | str]
        ] = [["keyup"] * len(release_keys)]
        release_keys = [release_keys]

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
    # keys : [direction] * N repeat
    # events : [keydown] * N repeat
    # delays : [0.5] + [D] * (N-1) repeat
    # DONE

    # Single + Secondary direction (ARF - secondary)
    # keys : [direction, secondary_direction] + [secondary_direction] * N repeat
    # events : [keydown, keydown] + [keydown] * N repeat
    # delays : [0.5] + [D] * (N-1) repeat
    # DONE

    # Single + Jump Hold (ARF - jump)
    # keys : [direction, jump] + [jump] * N repeat
    # events : [keydown, keydown] + [keydown] * N repeat
    # delays : [0.5] + [D] * (N-1) repeat
    # DONE

    # Single + Secondary + Jump Hold (ARF - jump)
    # keys : [direction, secondary_direction, jump] + [jump] * N repeat
    # events : [keydown, keydown, keydown] + [keydown] * N repeat
    # delays : [0.5] + [D] * (N-1) repeat
    # DONE

    # Single + Second Key Hold (ARF - Second key)
    # TODO - Test with Teleporting!
    # keys : [direction, secondary_key_press] + [secondary_key_press] * N repeat
    # events : [keydown, keydown] + [keydown] * N repeat
    # delays : [0.5] + [D] * (N-1) repeat
    # DONE

    # Single + Jump interval (No ARF)
    # keys : [direction, jump] + [jump] + [jump] + [jump] + ...
    # events : [keydown, keydown] + [keyup] + [keydown] + [keyup] + ...
    # delays : [2D] + [I] + [2D] + [I] + ...
    # DONE

    # Single + Secondary + interval jump (No ARF)
    # keys : [direction, secondary_direction, jump] + [jump] + [jump] + [jump] + ...
    # events : [keydown, keydown, keydown] + [keyup] + [keydown] + [keyup] + ...
    # delays : [2D] + [I] + [2D] + [I] + ...
    # DONE

    # Single + (Jump interval + Second Key interval) (combined) (No ARF)
    # TODO - Test this with jump+attack
    # keys : [direction] + [jump, secondary_key_press] + [jump, secondary_key_press] + ...
    # events : [keydown] + [keydown, keydown] + [keyup, keyup] + ...
    # delays : [0.25] + [2D] + [I] + [2D] + [I] + ...
    # DONE

    # Single + Jump interval + Second Key interval (not combined) (No ARF)
    # TODO - Test this with FJ once available, or with jump + heal
    # keys : [direction, jump] + [jump] + [secondary_key_press] + [secondary_key_press]
    # + [jump] + [jump] + [secondary_key_press] + [secondary_key_press] + ...
    # events : [keydown, keydown] + [keyup] + [keydown] + [keyup] + [keydown] + [keyup] + ...
    # delays : [2D] + [I/2] + [2D] + [I/2] + [2D] + [I/2] + ...

    # Single + Secondary direction + Jump interval + Second Key interval (not combined) (No ARF)
    # TODO - Test this with FJ once available (FJ into rope)
    # keys : [direction, secondary_direction, jump] + [jump] + [secondary_key_press] + [secondary_key_press]
    # + [jump] + [jump] + [secondary_key_press] + [secondary_key_press] + ...
    # events : [keydown, keydown, keydown] + [keyup] + [keydown] + [keyup] + [keydown] + [keyup] + ...
    # delays : [2D] + [I] + [2D] + [I] + [2D] + [I] + ...

    # Single + Second Key interval (No ARF)
    # TODO - Test with teleporting!
    # keys : [direction, secondary_key_press] + [secondary_key_press] + [secondary_key_press] + ...
    # events : [keydown, keydown] + [keyup] + [keydown] + [keyup] + ...
    # delays : [2D] + [I] + [2D] + [I] + ...
    # DONE

    # Single + Second Key interval + Third Key interval (No ARF)
    # TODO - test by telecasting
    # keys : [direction, secondary_key_press, tertiary_key_press] + [secondary_key_press, tertiary_key_press] + ...
    # events : [keydown, keydown, keydown] + [keyup, keyup] + ...
    # delays : [2D] + [I] + [2D] + [I] + ...
    # DONE

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
