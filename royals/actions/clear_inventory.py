import asyncio
import numpy as np
import random

from botting.core import controller
from botting.utilities import take_screenshot

from royals.maps import RoyalsMap
from royals.models_implementations.mechanics import MinimapConnection
from royals.models_implementations.mechanics.path_into_movements import get_to_target


async def cast_door_and_enter(
    handle: int,
    ign: str,
    door_key: str,
    current_map: RoyalsMap,
    allow_teleport: bool
):
    """
    Use door and enter it.
    There is no guarantee that the entering is properly made, since character may
    get knocked-back while this function is running.
    :param handle: Handle to the window
    :param ign: IGN of the character, used to retrieve jump key if required
    :param door_key: Key to press to open-up door.
    :param current_map: Current map object.
    :param allow_teleport: Whether to allow teleporting.
    :return:
    """

    # Create grid for the nearest town and retrieve current grid as well
    current_map.nearest_town.minimap.generate_grid_template(allow_teleport)
    town_grid = current_map.nearest_town.minimap.grid
    curr_grid = current_map.minimap.grid
    curr_minimap_img = current_map.minimap.title_img
    curr_title_box = current_map.minimap.get_minimap_title_box(handle)

    # Add a custom connection 'PORTAL' between current location and town grid.
    # The actual location in town is irrelevant for now (it can theoretically vary based
    # on where mystic door spawns)
    current_location = current_map.minimap.get_character_positions(handle).pop()
    curr_grid.node(*current_location).connect(
        town_grid.node(0, 0), connection_type=MinimapConnection.PORTAL
    )

    # Cast Door
    await controller.press(handle, door_key, silenced=True, cooldown=0.5)

    while np.array_equal(take_screenshot(handle, curr_title_box), curr_minimap_img):
        # As long as minimap title img is equal to its expected title,
        # we have not entered the door.
        actions = get_to_target(
            current_location,
            (0, 0),  # TODO - Figure out how to connect to another grid
            current_map.minimap
        )


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
