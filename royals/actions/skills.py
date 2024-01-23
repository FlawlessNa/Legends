from botting.core import controller
from botting.models_abstractions import Skill

from typing import Literal


async def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    direction: str = None,
    attacking_skill: bool = False
) -> None:
    """
    Casts a skill in a given direction. Updates game status.
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :param double_cast:
    :param attacking_skill:
    :return:
    """
    # TODO - Better handling of direction.
    if skill.unidirectional:
        await controller.press(
            handle,
            direction if direction else "left",
            silenced=False,
            enforce_delay=True,
            cooldown=0,
        )

    if attacking_skill:
        # Hold the key for about 0.1s to ensure skill goes through even if char gets hit
        # at the same time
        # Also, no silencing on attacking skills.
        try:
            await controller.press(
                handle,
                skill.key_bind(ign),
                silenced=False,
                cooldown=0.1,
                down_or_up="keydown"
            )
        finally:
            # Ensures the key is released
            await controller.press(
                handle,
                skill.key_bind(ign),
                silenced=False,
                cooldown=skill.animation_time - 0.1,
                down_or_up="keyup"
            )
    else:
        await controller.press(
            handle,
            skill.key_bind(ign),
            silenced=True,
            cooldown=skill.animation_time,
        )


async def teleport(
    handle: int,
    ign: str,
    direction: str,
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
    try:
        await controller.press(handle, direction, cooldown=0, down_or_up="keydown")
        await controller.press(
            handle, teleport_skill.key_bind(ign), cooldown=teleport_skill.animation_time
        )
    finally:
        await controller.press(handle, direction, cooldown=0, down_or_up="keyup")


async def telecast(
    handle: int, ign: str, direction: str, teleport_skill: Skill, ultimate_skill: Skill
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
    try:
        await controller.press(handle, direction, cooldown=0, down_or_up="keydown")
        await controller.press(
            handle, teleport_skill.key_bind(ign), cooldown=0, down_or_up="keydown"
        )
        await controller.press(
            handle, ultimate_skill.key_bind(ign), cooldown=0, down_or_up="keydown"
        )
    finally:
        await controller.press(handle, direction, cooldown=0, down_or_up="keyup")
        await controller.press(
            handle, teleport_skill.key_bind(ign), cooldown=0, down_or_up="keyup"
        )
        await controller.press(
            handle,
            ultimate_skill.key_bind(ign),
            cooldown=teleport_skill.animation_time,
            down_or_up="keyup",
        )
