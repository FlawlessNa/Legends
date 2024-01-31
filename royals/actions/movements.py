import random
from botting.core import controller
from typing import Literal


async def jump_on_rope(
    handle: int, ign: str, direction: Literal["left", "right"],
) -> None:
    """
    Jumps on a rope.
    :param handle: Handle of the game.
    :param ign: IGN of the character.
    :param direction: Direction to jump in.
    :return:
    """
    await controller.move(
        handle,
        ign,
        direction,
        0.1,
        "up",
        True,
        jump_interval=0.1
    )


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
        handle, ign, direction, duration=0.05, jump=True, jump_interval=0.05
    )
