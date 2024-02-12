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
) -> None:
    """
    Casts a skill and triggers the keyboard repeat feature for the duration.
    If skill is unidirectional, then first turn into the provided direction.
    The 0.5 standard first delay is automatically added, since event for consecutive
    casts of the same skill the key is always released at the end.
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :param ready_at:
    :return:
    """
    delays = [0.5]
    while sum(delays) < skill.animation_time:
        delays.append(next(controller.random_delay))
    # The last delay is between keydown and keyup, which is doubled
    delays[-1] *= 2

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
    if "up" in pressed and direction in ["left", "right"]:
        time.sleep(0.1)  # Ensures a little buffer before releasing any prior keys
    keys = [direction, teleport_skill.key_bind(ign), teleport_skill.key_bind(ign)]
    events: list[Literal] = ["keydown", "keydown", "keyup"]
    delays = [next(controller.random_delay) * 2]
    while sum(delays) < teleport_skill.animation_time * num_times:
        delays.extend([next(controller.random_delay) * 2 for _ in range(2)])
        keys.extend([teleport_skill.key_bind(ign), teleport_skill.key_bind(ign)])
        events.extend(["keydown", "keyup"])
    # delays = [next(controller.random_delay) for _ in range(2)] + [
    #     teleport_skill.animation_time
    # ]
    # for _ in range(num_times - 1):
    #     keys.extend([teleport_skill.key_bind(ign), teleport_skill.key_bind(ign)])
    #     events.extend(["keydown", "keyup"])
    #     delays.extend(
    #         [next(controller.random_delay) * 2, teleport_skill.animation_time]
    #     )

    structure = controller.input_constructor(handle, keys, events)
    if direction in ["left", "right"]:
        release = controller.release_opposites(handle, direction, "up", "down")
    else:
        release = controller.release_opposites(handle, direction, "left", "right")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)
    await controller.focused_inputs(handle, structure, delays, 1)


async def telecast(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    ultimate_skill: Skill,
):
    """
    Teleport while casting ultimate in a given direction.
    :param handle:
    :param ign:
    :param direction:
    :param teleport_skill:
    :param ultimate_skill:
    :return:
    """
    pressed = controller.get_held_movement_keys(handle)
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
        events.extend(
            [
                ["keydown", "keydown"],
                ["keyup", "keyup"]
            ]
        )

    structure = controller.input_constructor(handle, keys, events)
    if direction in ["left", "right"]:
        release = controller.release_opposites(handle, direction, "up", "down")
    else:
        release = controller.release_opposites(handle, direction, "left", "right")
    if release:
        structure.insert(0, release)
        delays.insert(0, 0)
    await controller.focused_inputs(handle, structure, delays, 1)
    #
    # start = time.perf_counter()
    # if duration is None:
    #     duration = ultimate_skill.animation_time
    # else:
    #     assert (
    #         duration < ultimate_skill.animation_time
    #     ), "Duration must be less than ultimate skill animation time."
    #
    # async def _coro():
    #     for direction in directions:
    #         await controller.move(
    #             handle,
    #             ign,
    #             direction,
    #             teleport_skill.animation_time,
    #             secondary_key_press=teleport_skill.key_bind(ign),
    #             tertiary_key_press=ultimate_skill.key_bind(ign),
    #             secondary_key_interval=teleport_skill.animation_time,
    #         )
    #
    # try:
    #     await asyncio.wait_for(_coro(), timeout=duration)
    # except asyncio.TimeoutError:
    #     pass
    # finally:
    #     await asyncio.sleep(
    #         max(0.0, ultimate_skill.animation_time - (time.perf_counter() - start))
    #     )
