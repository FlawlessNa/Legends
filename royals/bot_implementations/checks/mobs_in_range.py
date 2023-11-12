import itertools
import numpy as np

from typing import Sequence
from royals.game_model import BaseMob


def mob_count_in_img(img: np.ndarray,
                     mobs: list[BaseMob]) -> int:
    """
    Given an image of arbitrary size, return the mob count of a specific mob found within that image.
    :param img: Potentially cropped image based on current character position and skill range.
    :param mobs: The mobs to look for.
    :return: Total number of mobs detected in the image
    """
    return sum([mob.get_mob_count(img) for mob in mobs])


def get_mobs_positions_in_img(img: np.ndarray,
                              mobs: list[BaseMob]) -> list[Sequence[int]]:
    """
    Given an image of arbitrary size, return the positions of a specific mob found within that image.
    :param img: Potentially cropped image based on current character position and skill range.
    :param mobs: The mobs to look for.
    :return: List of mob positions found in the image.
    """
    return list(itertools.chain(*mob.get_onscreen_mobs(img) for mob in mobs))


def get_closest_mob_direction(character_pos: Sequence[int],
                              mobs: list[Sequence[int]]) -> str | None:
    """
    Given current character position and list of detected mobs on screen,
    return the (horizontal) direction of the closest mob relative to character.
    :param character_pos: Rectangle (x, y, w, h)
    :param mobs: List of rectangles (x, y, w, h)
    :return: Direction of closest mob relative to character.
    """
    if not mobs:
        return None
    centers = [mob[0] + mob[2] / 2 for mob in mobs]
    distances = [center - character_pos[0] - character_pos[2] / 2 for center in centers]
    # Find minimum distance in terms of absolute value, but retain its sign
    closest_mob_idx = np.argmin(np.abs(distances))
    return 'left' if distances[closest_mob_idx] < 0 else 'right'
