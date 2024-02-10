import random
from botting.core import controller
from typing import Literal


async def single_jump(
    handle: int, direction: Literal["left", "right", "up", "down"], jump_key: str
) -> None:



async def continuous_jump(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    jump_key: str,
    num_jumps: int
) -> None:
    raise NotImplementedError


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
    # await asyncio.sleep(0.25)  # Buffer to avoid previous movements to interfere
    await controller.move(
        handle,
        ign,
        direction,
        0.75,
        "up",
        True,
        jump_interval=0.75
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
        handle, ign, direction, duration=0.5, jump=True, jump_interval=0.5
    )
