from royals.game_model import BaseMap
from typing import Coroutine


def get_to_target_pos(current: tuple[float, float],
                      target: tuple[float, float],
                      in_game_map: BaseMap) -> Coroutine:
    """
    Computes the path from current to target using map features.
    Returns a coroutine that will move the character to the target position.
    :param current: Character position on minimap.
    :param target: Target position on minimap.
    :param in_game_map: Map which contains minimap coordinates for all existing features.
    :return: A series of awaitables (wrapped in a coroutine) used to move character to target position.
    """
    pass

