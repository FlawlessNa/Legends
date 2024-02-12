import random
import time
from botting.core import controller
from typing import Literal


async def move(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    secondary_direction: Literal["up", "down"] = None,
    *,
    duration: float,
) -> None:
    """
    Triggers the automatic repeat feature in a given direction.
    The 0.5 first standard delay is not added by default, since the key may already
    be held down.
    :param handle:
    :param direction:
    :param duration:
    :param secondary_direction:
    :return:
    """
    # TODO - First 0.5 standard delay in new direction cases
    delays = []
    while sum(delays) < duration:
        delays.append(next(controller.random_delay))
    if secondary_direction is not None:
        keys = [[direction, secondary_direction]]
        keys.extend([secondary_direction] * (len(delays) - 1))
        events = [["keydown", "keydown"]]
        events.extend(["keydown"] * (len(delays) - 1))
    else:
        keys = [direction] * len(delays)
        events: list[Literal] = ["keydown"] * len(delays)
    structure = controller.input_constructor(handle, keys, events)

    if secondary_direction:
        release = controller.release_opposites(handle, direction, secondary_direction)
    elif direction in ["left", "right"]:
        release = controller.release_opposites(handle, direction, "up", "down")
        if "up" in controller.get_held_movement_keys(handle):
            time.sleep(0.1)
    else:
        release = controller.release_opposites(handle, direction, "left", "right")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)
    await controller.focused_inputs(hwnd=handle, inputs=structure, delays=delays)


async def single_jump(
    handle: int, direction: Literal["left", "right", "up", "down"], jump_key: str
) -> None:
    """
    Jump once in a given direction. The direction key is not released.
    :param handle:
    :param direction:
    :param jump_key:
    :return:
    """
    pressed = controller.get_held_movement_keys(handle)
    if direction in ["left", "right"]:
        if direction in pressed and controller.OPPOSITES[direction] not in pressed:
            keys = [jump_key, jump_key]
            events: list[Literal["keydown", "keyup"]] = ["keydown", "keyup"]
            delays = [next(controller.random_delay) * 2, 0.75]
        elif controller.OPPOSITES[direction] in pressed:
            keys = [direction, jump_key, jump_key]
            events: list[Literal["keydown", "keyup"]] = ["keydown", "keydown", "keyup"]
            delays = [0.15, next(controller.random_delay) * 2, 0.75]
        else:
            keys = [direction, jump_key, jump_key]
            events: list[Literal["keydown", "keyup"]] = ["keydown", "keydown", "keyup"]
            delays = [next(controller.random_delay) * 2 for _ in range(2)] + [0.75]
    elif direction == 'down':
        # Special case where we voluntarily trigger the automatic repeat feature
        # to avoid static position.
        keys = [direction, jump_key, jump_key]
        events: list[Literal["keydown", "keyup"]] = ["keydown", "keydown", "keyup"]
        delays = [next(controller.random_delay) * 2 for _ in range(3)]
        while sum(delays) < 0.75:
            keys.extend([jump_key, jump_key])
            events.extend(["keydown", "keyup"])
            delays.extend([next(controller.random_delay) * 2 for _ in range(2)])
    else:
        keys = [direction, jump_key, jump_key]
        events: list[Literal["keydown", "keyup"]] = ["keydown", "keydown", "keyup"]
        delays = [next(controller.random_delay) * 2 for _ in range(2)] + [0.75]

    structure = controller.input_constructor(handle, keys, events)
    if direction in ["up", "down"]:
        release = controller.release_opposites(handle, direction, "left", "right")
    else:
        release = controller.release_opposites(handle, direction, "up", "down")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)
    await controller.focused_inputs(
        handle, structure, delays, enforce_last_inputs=1, enforce_transition_delay=True
    )


async def continuous_jump(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    jump_key: str,
    num_jumps: int,
) -> None:
    raise NotImplementedError  # TODO: Implement this function and figure out delays


async def jump_on_rope(
    handle: int, direction: Literal["left", "right"], jump_key: str
) -> None:
    """
    Jump on a rope. The secondary direction is maintained after the jump.
    :param handle:
    :param direction:
    :param jump_key:
    :return:
    """
    pressed = controller.get_held_movement_keys(handle)
    if direction in pressed and controller.OPPOSITES[direction] not in pressed:
        keys = [[jump_key, "up"], [jump_key, direction]]
        events: list[Literal["keydown", "keyup"] | list] = [
            ["keydown", "keydown"],
            ["keyup", "keyup"],
        ]
        delays = [
            0.75,
            next(controller.random_delay) * 2
        ]

    elif controller.OPPOSITES[direction] in pressed:
        keys = [
            direction,
            [jump_key, "up"],
            [jump_key, direction],
        ]
        events: list[Literal["keydown", "keyup"] | list] = [
            "keydown",
            ["keydown", "keydown"],
            ["keyup", "keyup"],
        ]
        # Small buffer for direction change
        delays = [0.15, 0.75, next(controller.random_delay)]

    else:
        keys = [[direction, jump_key], "up", [jump_key, direction]]
        events: list[Literal["keydown", "keyup"] | list] = [
            ["keydown", "keydown"],
            "keydown",
            ["keyup", "keyup"],
        ]
        delays = [
            next(controller.random_delay) * 2,
            0.75,
            next(controller.random_delay)
        ]

    structure = controller.input_constructor(handle, keys, events)
    release = controller.release_opposites(handle, direction)
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)
    await controller.focused_inputs(
        handle, structure, delays, enforce_last_inputs=1, enforce_transition_delay=True
    )


async def random_jump(handle: int, jump_key: str):
    """
    Randomly jump in a direction. Used as a failsafe action when stuck
    in ladder or in an undefined node.
    :param handle:
    :param jump_key:
    :param kwargs:
    :return:
    """
    direction = random.choice(["left", "right"])
    await single_jump(handle, direction, jump_key)
