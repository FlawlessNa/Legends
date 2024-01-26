import asyncio
import random
from botting.core import controller


async def cast_door_and_enter(
    handle: int,
    door_key: str
):
    """
    Use door and enter it.
    There is no guarantee that the entering is properly made, since character may
    get knocked-back while this function is running.
    :param handle: Handle to the window
    :param door_key: Key to press to open-up door.
    :return:
    """
    # TODO - Test the cooldowns
    await controller.press(handle, door_key, silenced=True, cooldown=0.5)
    for _ in range(random.randint(2, 4)):
        await controller.press(handle, 'up', silenced=True)


async def go_to_town(
    handle: int,
    use_mystic_door: bool = True,
    mystic_door_key: str = None,
    inventory_toggle_key: str = None
) -> None:
    """
    Go to town by either using a mystic door and entering it, or by toggling the
    inventory and using a nearest town scroll.
    :param handle: Handle to the window
    :param use_mystic_door: Whether to use door or a town scroll.
    :param mystic_door_key: Keybindings for mystic door.
    :param inventory_toggle_key: Keybindings to toggle inventory.
    :return: None
    """
    if not use_mystic_door:
        raise NotImplementedError
