import asyncio
from botting.core import controller


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
    pass
