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
    attacking_skill: bool = False,
) -> None:
    """
    Casts a skill and optionally change direction beforehand.
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :param attacking_skill:
    :return:
    """
    # TODO - Better handling of direction.
    if skill.unidirectional:
        await controller.move(
            handle,
            ign,
            direction if direction else "left",
            duration=0.05,
        )

    if attacking_skill:
        # Failsafe to ensure properly cast
        await controller.press(
            handle,
            skill.key_bind(ign),
            silenced=False,
            delay=0,
        )
        first_sleep = min(0.3, skill.animation_time)
        await asyncio.sleep(first_sleep)
        await controller.press(
            handle,
            skill.key_bind(ign),
            silenced=True,
            delay=0,
        )
        await asyncio.sleep(max(skill.animation_time - first_sleep, 0.0))

    else:
        await controller.press(
            handle,
            skill.key_bind(ign),
            silenced=False,
        )
        await asyncio.sleep(skill.animation_time)


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
        print(time.perf_counter() - start)
