from botting.core import controller
from royals.models_implementations import Skill


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
