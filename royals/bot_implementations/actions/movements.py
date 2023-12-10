import asyncio
from botting.core.controls import controller
from typing import Literal


async def jump_on_rope(
    handle: int, ign: str, direction: Literal["left", "right"], **kwargs
) -> None:
    """
    Jumps on a rope.
    :param handle: Handle of the game.
    :param direction: Direction to jump in.
    :param kwargs: Keyword arguments to pass to the controller.
    :return:
    """

    await controller.press(handle, "up", cooldown=0, down_or_up="keydown")
    await controller.move(handle, ign, direction, jump=True, enforce_delay=False, duration=0.05)
    await asyncio.sleep(0.5)
    await controller.press(handle, "up", cooldown=0, down_or_up="keyup")
