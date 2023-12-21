from botting.core import controller
from royals.models_implementations import Skill

from typing import Literal


async def cast_skill(handle: int, ign: str, skill: Skill, direction: str = None) -> None:
    """
    Casts a skill in a given direction. Updates game status.
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :return:
    """
    # TODO - Better handling of direction.
    if skill.unidirectional:
        await controller.press(handle, direction, silenced=False, enforce_delay=True)
    # data.update(
    #     current_direction=direction
    # )  # TODO - Add this piece into the QueueAction wrapping instead
    await controller.press(
        handle,
        skill.key_bind(ign),
        silenced=True,
        cooldown=skill.animation_time,
    )


async def teleport(
    handle: int, ign: str, direction: Literal["left", "right", "down", "up"], teleport_skill: Skill
):
    """
    Casts teleport in a given direction.
    :param handle:
    :param ign:
    :param teleport_skill:
    :param direction:
    :return:
    """
    try:
        await controller.press(handle, direction, cooldown=0, down_or_up="keydown")
        await controller.press(handle, teleport_skill.key_bind(ign), cooldown=teleport_skill.animation_time)
    finally:
        await controller.press(handle, direction, cooldown=0, down_or_up="keyup")
