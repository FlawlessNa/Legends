import asyncio
import time
from typing import Literal

from botting.core import controller
from botting.models_abstractions import Skill


async def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    direction: str = None,
) -> None:
    """
    Casts a skill and triggers the keyboard repeat feature for the duration.
    If skill is unidirectional, then first turn into the provided direction.
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :return:
    """
    delays = [0.5]
    while sum(delays) < skill.animation_time:
        delays.append(next(controller.random_delay))
    # The last delay is between keydown and keyup, which is doubled
    # TODO - See if a delay or two should be removed to avoid a double-cast
    delays[-1] *= 2

    keys = [skill.key_bind(ign)] * len(delays)
    events: list[Literal["keydown", "keyup"]] = ["keydown"]
    [events.append("keydown") for _ in range(len(delays) - 2)]  # TODO - see if better way (this is to avoid "invalid type" from IDE)
    events.append("keyup")

    if direction is not None and skill.unidirectional:
        # TODO - Generic function to release other directions based on their status
        events.insert(0, "keydown")
        events.insert(0, "keyup")
        keys.insert(0, direction)
        keys.insert(0, direction)
        delays.append(2 * next(controller.random_delay))
        delays.append(next(controller.random_delay))

    structure = controller.input_constructor(handle, keys, events)
    try:
        await asyncio.wait_for(
            controller.focused_inputs(handle, structure, delays, 1),
            timeout=min(skill.animation_time * 0.95, skill.animation_time - 0.05)
        )
    except TimeoutError:
        print(f'Timeout from cast_skill {ign} {skill.name}')

    except asyncio.CancelledError:
        print(f'cast_skill Cancelled {ign} {skill.name}')

async def teleport_once(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
):
    """
    Casts teleport in a given direction.
    :param handle:
    :param ign:
    :param teleport_skill:
    :param direction:
    :return:
    """
    start = time.perf_counter()
    try:
        await controller.move(
            handle,
            ign,
            direction,
            duration=0.5,
            secondary_key_press=teleport_skill.key_bind(ign),
            secondary_key_interval=teleport_skill.animation_time,
        )
    finally:
        await asyncio.sleep(
            max(0.0, teleport_skill.animation_time - (time.perf_counter() - start))
        )


async def continuous_teleport(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    num_times: int,
):
    """
    Continuously casts teleport in a given direction.
    :param handle:
    :param ign:
    :param direction:
    :param teleport_skill:
    :param num_times:
    :return:
    """
    duration = teleport_skill.animation_time * num_times
    await controller.move(
        handle,
        ign,
        direction,
        duration=duration,
        secondary_key_press=teleport_skill.key_bind(ign),
    )


async def telecast(
    handle: int,
    ign: str,
    directions: list[Literal["left", "right", "up", "down"]],
    teleport_skill: Skill,
    ultimate_skill: Skill,
    duration: float = None,
):
    """
    Teleport while casting ultimate in a given direction.
    :param handle:
    :param ign:
    :param directions:
    :param teleport_skill:
    :param ultimate_skill:
    :param duration:
    :return:
    """
    start = time.perf_counter()
    if duration is None:
        duration = ultimate_skill.animation_time
    else:
        assert (
            duration < ultimate_skill.animation_time
        ), "Duration must be less than ultimate skill animation time."

    async def _coro():
        for direction in directions:
            await controller.move(
                handle,
                ign,
                direction,
                teleport_skill.animation_time,
                secondary_key_press=teleport_skill.key_bind(ign),
                tertiary_key_press=ultimate_skill.key_bind(ign),
                secondary_key_interval=teleport_skill.animation_time,
            )

    try:
        await asyncio.wait_for(_coro(), timeout=duration)
    except asyncio.TimeoutError:
        pass
    finally:
        await asyncio.sleep(
            max(0.0, ultimate_skill.animation_time - (time.perf_counter() - start))
        )
