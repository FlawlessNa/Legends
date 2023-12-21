import asyncio
import random
from botting.core.controls import controller
from typing import Literal


async def jump_on_rope(
    handle: int, ign: str, direction: Literal["left", "right"], **kwargs
) -> None:
    """
    Jumps on a rope.
    :param handle: Handle of the game.
    :param ign: IGN of the character.
    :param direction: Direction to jump in.
    :param kwargs: Keyword arguments to pass to the controller.
    :return:
    """
    try:
        await controller.press(handle, "up", cooldown=0, down_or_up="keydown")
        await controller.move(
            handle, ign, direction, jump=True, enforce_delay=False, duration=0.05
        )
        await asyncio.sleep(0.5)
    finally:
        await controller.press(handle, "up", cooldown=0, down_or_up="keyup")


async def random_jump(handle: int, ign: str, **kwargs):
    """
    Randomly jump in a direction. Used as a failsafe action when stuck
    in ladder or in an undefined node.
    :param handle:
    :param ign:
    :param kwargs:
    :return:
    """
    direction = random.choice(["left", "right"])
    await controller.move(
        handle, ign, direction, jump=True, enforce_delay=False, duration=0.05, **kwargs
    )

