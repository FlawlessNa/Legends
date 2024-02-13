"""
Skill related actions.
These should always ensure skill keys are released at the end.
"""
import asyncio
import time
from typing import Literal

from botting.core import controller
from botting.models_abstractions import Skill


async def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    ready_at: float,
    direction: str = None,
    single_press: bool = False,
) -> None:
    """
    Casts a skill and triggers the keyboard repeat feature for the duration.
    If skill is unidirectional, then first turn into the provided direction.
    The 0.5 standard first delay is automatically added, since event for consecutive
    casts of the same skill the key is always released at the end.
    :param handle:
    :param ign:
    :param skill:
    :param ready_at:
    :param direction:
    :param single_press:
    :return:
    """
    if single_press:
        await controller.press(handle, skill.key_bind(ign), silenced=True)
        await asyncio.sleep(skill.animation_time)
        return
    delays = []  # TODO - First 0.5 standard delay in new direction cases
    while sum(delays) < skill.animation_time:
        delays.append(next(controller.random_delay))
    # The last delay is between keydown and keyup, which is doubled
    delays[-1] *= 2

    pressed = controller.get_held_movement_keys(handle)
    keys = [skill.key_bind(ign)] * len(delays)
    events: list[Literal["keydown", "keyup"]] = ["keydown"]
    [
        events.append("keydown") for _ in range(len(delays) - 2)
    ]  # TODO - see if better way (this is to avoid "invalid type" from IDE)
    events.append("keyup")

    if direction is not None and skill.unidirectional:
        # TODO - Generic function to release other directions based on their status
        events.insert(0, "keydown")
        events.insert(1, "keyup")
        keys.insert(0, direction)
        keys.insert(0, direction)
        delays.append(2 * next(controller.random_delay))
        delays.append(next(controller.random_delay))

    # Release down key even if going downwards to ensure character isn't crouching
    if 'down' in pressed:
        keys.insert(0, 'down')
        events.insert(0, 'keyup')
        delays.insert(0, next(controller.random_delay) * 2)

    structure = controller.input_constructor(handle, keys, events)

    wait_time = max(ready_at - time.perf_counter(), 0.0)
    if wait_time > 0:
        await asyncio.sleep(wait_time)

    await asyncio.wait_for(
        controller.focused_inputs(handle, structure, delays, 1),
        timeout=min(skill.animation_time * 0.95, skill.animation_time - 0.05),
    )


async def ultimate_cast():
    """
    TODO.
    Use this in the context of farming.
    In this context, fire focus_inputs with a single structure at a time, such that
    lock is always released. This enables mage to cast nearly simultaneously without
    cancelling each other such that they may still press more than once to ensure proper
    cast.
    :return:
    """
    pass


async def teleport(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    num_times: int = 1,
):
    """
    Casts teleport in a given direction.
    :param handle:
    :param ign:
    :param teleport_skill:
    :param direction:
    :param num_times:
    :return:
    """
    pressed = controller.get_held_movement_keys(handle)
    enforce_last_inputs = 1
    if "up" in pressed and direction in ["left", "right"]:
        time.sleep(0.1)  # Ensures a little buffer before releasing any prior keys
    keys = [direction, teleport_skill.key_bind(ign), teleport_skill.key_bind(ign)]
    events: list[Literal] = ["keydown", "keydown", "keyup"]
    delays = [next(controller.random_delay) * 2]

    while sum(delays) < teleport_skill.animation_time * num_times:
        delays.extend([next(controller.random_delay) * 2 for _ in range(2)])
        keys.extend([teleport_skill.key_bind(ign), teleport_skill.key_bind(ign)])
        events.extend(["keydown", "keyup"])

    if direction == "down":
        keys.append(direction)
        events.append("keyup")
        delays.append(0)
        enforce_last_inputs = 2

    structure = controller.input_constructor(handle, keys, events)
    if direction in ["left", "right"]:
        release = controller.release_opposites(handle, direction, "up", "down")
    else:
        release = controller.release_opposites(handle, direction, "left", "right")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)

    await controller.focused_inputs(handle, structure, delays, enforce_last_inputs)


async def telecast(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    ultimate_skill: Skill,
    ready_at: float,
):
    """
    Teleport while casting ultimate in a given direction.
    :param handle:
    :param ign:
    :param direction:
    :param teleport_skill:
    :param ultimate_skill:
    :param ready_at:
    :return:
    """
    pressed = controller.get_held_movement_keys(handle)
    enforce_last_inputs = 1
    if "up" in pressed and direction in ["left", "right"]:
        time.sleep(0.1)  # Ensures a little buffer before releasing any prior keys

    keys = [
        [direction, teleport_skill.key_bind(ign), ultimate_skill.key_bind(ign)],
        [teleport_skill.key_bind(ign), ultimate_skill.key_bind(ign)],
    ]
    events: list[Literal | list] = [
        ["keydown", "keydown", "keydown"],
        ["keyup", "keyup"],
    ]
    delays = [next(controller.random_delay) * 2 for _ in range(2)]
    while sum(delays) < teleport_skill.animation_time:
        delays.extend([next(controller.random_delay) * 2 for _ in range(2)])
        keys.extend(
            [
                [teleport_skill.key_bind(ign), ultimate_skill.key_bind(ign)],
                [teleport_skill.key_bind(ign), ultimate_skill.key_bind(ign)],
            ]
        )
        events.extend([["keydown", "keydown"], ["keyup", "keyup"]])

    # Release down key even if going downwards to ensure character isn't crouching
    if 'down' in pressed:
        keys.insert(0, 'down')
        events.insert(0, 'keyup')
        delays.insert(0, next(controller.random_delay) * 2)

    if direction == "down":
        keys.append(direction)
        events.append("keyup")
        delays.append(0)
        enforce_last_inputs = 2

    structure = controller.input_constructor(handle, keys, events)
    if direction in ["left", "right"]:
        release = controller.release_opposites(handle, direction, "up", "down")
    else:
        release = controller.release_opposites(handle, direction, "left", "right")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)

    wait_time = max(ready_at + 0.1 - time.perf_counter(), 0.0)
    if wait_time > 0:
        print("Waiting", wait_time, "seconds before telecasting")
        await asyncio.sleep(wait_time)
    await controller.focused_inputs(handle, structure, delays, enforce_last_inputs)

