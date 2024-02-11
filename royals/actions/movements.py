import random
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
    keys = [direction, jump_key, jump_key]
    events: list[Literal["keydown", "keyup"]] = ["keydown", "keydown", "keyup"]

    # twice delay between direction & jump, and twice delay between keydown/up
    delays = [next(controller.random_delay) * 2 for _ in range(2)] + [
        0.75  # TODO - check if this needs improvement
    ]
    structure = controller.input_constructor(handle, keys, events)
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
    keys = [[direction, "up"], jump_key, [jump_key, direction]]
    events: list[Literal["keydown", "keyup"] | list] = [
        ["keydown", "keydown"],
        "keydown",
        ["keyup", "keyup"],
    ]

    # Long delay between keydowns and ups, to maximize chances of grabbing rope
    delays = [next(controller.random_delay) * 2, 0.75, next(controller.random_delay)]
    structure = controller.input_constructor(handle, keys, events)
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
