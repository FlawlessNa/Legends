"""
Controller module for the game. Contains all high-level functions necessary for interacting with the game.
The .inputs submodule contains all low-level code required to build these (complex) high level functions.
"""
import asyncio
import functools
import logging
import win32con
from typing import Literal

from .inputs import focused_input, non_focused_input

from royals.utilities import config_reader, randomize_params

logger = logging.getLogger(__name__)


@functools.lru_cache
def key_binds(ign: str) -> dict[str, str]:
    """
    Retrieves the key bindings for the associated character from the keybindings config file.
    The configs cannot be changed while the bot is running. In-game key binds should therefore not be changed either.
    """
    temp = {
        k: eval(v) for k, v in dict(config_reader("keybindings", f"{ign}")).items()
    }
    final = {}
    for val in temp.values():
        final.update(val)
    logger.debug(f"Key bindings successfully retrieved for {ign}.")
    return final


async def press(
    handle: int,
    key: str,
    silenced: bool = False,
    cooldown: float = 0.1,
    enforce_delay: bool = False,
    **kwargs,
) -> None:
    """
    # TODO - deal with keys/skills/macros variants
    :param handle: Window handle to the process.
    :param key: String representation of the key to be pressed.
    :param silenced: Whether to activate the window before pressing the key. If True, the key is sent through PostMessage(...) instead of SendInput(...).
    :param cooldown: Delay between each call to this function. However, several keys/inputs may be sent at once, and cooldown is only applied at the very end.
        Note: To control delay between each keys/inputs on a single call, pass in 'delay' as a keyword argument. Each delay will be slightly randomized.
    :param enforce_delay: Only applicable when silenced = False. If several inputs are sent at once, this will enforce a delay between each input. Otherwise, they are all simultaneous.
    :return: None
    """
    if silenced:
        await non_focused_input(
            handle,
            key,
            [win32con.WM_KEYDOWN, win32con.WM_KEYUP],
            cooldown=cooldown,
            **kwargs,
        )
    else:
        await focused_input(
            handle,
            key,
            ["keydown", "keyup"],
            cooldown=cooldown,
            enforce_delay=enforce_delay,
            **kwargs,
        )


async def write(
    handle: int,
    message: str,
    silenced: bool = True,
    cooldown: float = 0.1,
    enforce_delay: bool = True,
    **kwargs,
) -> None:
    """
    Write a message in the specified window. When silenced=True, We use the WM_CHAR command to allow for differentiation of lower and upper case letters. This by-passes the KEYDOWN/KEYUP commands.
    Therefore, this creates "non-human" inputs sent to the window and as such, should only be used to actually write stuff in the chat and nothing else (anti-detection prevention).
    Additionally, when silenced=False, the SendInput function creates VK_PACKETS with are sent to the window to replicate any custom chars. This also creates "non-human" behavior.
    :param handle: Window handle to the process.
    :param message: Actual message to be typed.
    :param silenced: Whether to write input to the active window or not. If True, the key is sent through PostMessage(...) instead of SendInput(...).
    :param cooldown: Delay between each call to this function.
    :param enforce_delay: Only used when silenced=False. If false, the entire message is written instantly (looks like a copy/paste). If True, a delay is enforced between each char.
    :return: None
    """
    if silenced:
        logger.info(f"Writing message {message} in window {handle} silently.")
        await non_focused_input(
            handle,
            list(message),
            [win32con.WM_CHAR] * len(message),
            cooldown=cooldown,
            **kwargs,
        )

    else:
        logger.info(f"Writing message {message} in window {handle} LOUDLY.")
        message = [char for char in list(message) for _ in range(2)]
        events: list[Literal] = ["keydown", "keyup"] * (len(message) // 2)
        await focused_input(
            handle,
            list(message),
            events,
            cooldown=cooldown,
            as_unicode=True,
            enforce_delay=enforce_delay,
            **kwargs,
        )


@randomize_params("duration", "jump_interval")
async def move(
    handle: int,
    ign: str,  # TODO - Replace handle/ign by "who" -- Controller.move(who=...). Who is the IGN, and add a function to retrieve handles from IGNs and pass that dict into __init__.
    direction: Literal["left", "right", "up", "down"],
    duration: float,
    jump: bool = False,
    jump_interval: float = 0.5,
    secondary_direction: Literal["up", "down"] | None = None,
    delay: float = 0.033,
) -> None:
    """
    Requires focus (Note: the lock is only used once all the inputs have been constructed, so it is not necessary to keep the lock for the entire duration of the function).
    Moves the player in a given direction, for a given duration. If jump=True, the player will also jump periodically.
    Specifying a secondary direction can be used to enter portals, move up ladders, or jump down platforms.
    This function attempts to replicate human-like input as accurately as possible. It triggers the keyboard automatic repeat feature, which repeats the keydown event until the key is released.
    :param handle: Window handle to the process.
    :param ign: IGN of the character. Used to retrieve key bindings.
    :param direction: Direction in which to move.
    :param duration: Duration of the movement.
    :param jump: bool. Whether to jump periodically or not.
    :param jump_interval: Interval between each jump. Only used if jump=True.
    :param secondary_direction: Secondary direction to press. Only used if direction is 'left' or 'right'. May be used to jump up ladders, jump down platforms, or enter portals.
    :param delay: Default 0.033, which is somewhat equal to the keyboard automatic repeat feature as observed in Spy++ (on my PC setup).
    :return: None
    """
    assert direction in ("left", "right", "up", "down")
    assert secondary_direction in ("up", "down", None)
    if direction in ("up", "down"):
        assert secondary_direction is None

    # Max. number of events to send into input message stream. The real events sent will be less, because the "real-time" delays are usually longer than the specified delay.
    upper_bound = int(duration // delay)
    events: list[Literal] = ["keydown"] * upper_bound
    nbr_jumps = int(duration // jump_interval)
    jump_events = [win32con.WM_KEYDOWN, win32con.WM_KEYUP]
    repeated_direction = secondary_direction if secondary_direction else direction

    async def _jump_n_times(n: int) -> None:
        """Call the function multiple down, such that delay between keydown/keyup is small, but the cooldown between each jump is larger"""
        for _ in range(n):
            await non_focused_input(
                handle,
                key_binds(ign)["jump"],
                jump_events,
                cooldown=jump_interval,
                delay=0,
            )

    async def _combined_tasks() -> None:
        """The repeated keydown for direction/secondary direction is considered one task, the periodical jump is considered another. Wrap in a function to wait_for the entire task group."""
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                focused_input(
                    handle,
                    repeated_direction,
                    events,
                    cooldown=0,
                    enforce_delay=True,
                    delay=delay,
                )
            )
            if jump:
                tg.create_task(_jump_n_times(nbr_jumps))

    logger.debug(
        f"{ign} now moving {direction} for {duration} seconds. Jump={jump} and secondary direction={secondary_direction}."
    )
    # Press direction and secondary direction
    await focused_input(handle, direction, ["keydown"], enforce_delay=False)
    if secondary_direction:
        await focused_input(
            handle, secondary_direction, ["keydown"], enforce_delay=False
        )

    # wait_for at most "duration" on the automatic repeat feature simulation + periodical jump (if applicable)
    try:
        await asyncio.wait_for(_combined_tasks(), duration)
    except asyncio.TimeoutError:
        pass  # Simply stop the movement. This code is nearly always reached because the "real" delays are usually longer than the specified delays. This is because other tasks may be running.
    except Exception as e:
        raise
    finally:
        # Release all keys
        await focused_input(
            handle, direction, ["keyup"], enforce_delay=False, cooldown=0
        )
        if secondary_direction:
            await focused_input(
                handle,
                secondary_direction,
                ["keyup"],
                enforce_delay=False,
                cooldown=0,
            )
        if jump:
            await non_focused_input(
                handle, key_binds(ign)["jump"], [win32con.WM_KEYUP], cooldown=0
            )
        logger.debug(f"{ign} has successfully released movement keys.")


async def mouse_move() -> None:
    """Requires focus because otherwise the window may not properly register mouse movements. In such a case, if mouse blocks visuals, it will keep blocking them."""
    raise NotImplementedError


async def click() -> None:
    """Requires focus because otherwise the window may not properly register mouse movements. In such a case, if mouse blocks visuals, it will keep blocking them."""
    raise NotImplementedError
