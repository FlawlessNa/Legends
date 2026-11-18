"""
Mobs on screen: how many, where, and which way the closest one is. Plain
functions, which `MobsHitting`, the rotation's smart target and
`CheckMobsStillSpawn` call; they were `MobsHittingMixin`'s methods.
"""

import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from botting.models_abstractions import BaseMob
from maple.screen.position import Camera


def mob_count_in_img(
    img: np.ndarray,
    mobs: Sequence[BaseMob],
    handle: int,
    **kwargs: Any,  # noqa: ANN401
) -> int:
    """
    Given an image of arbitrary size, return the mob count of a specific mob found
    within that image.
    :param img: Image based on current character position and skill range.
    :param mobs: The mobs to look for.
    :param handle: The client the image is of.
    :return: Total number of mobs detected in the image
    """
    return sum([mob.get_mob_count(img, handle, **kwargs) for mob in mobs])


def get_mobs_positions_in_img(
    img: np.ndarray,
    mobs: Sequence[BaseMob],
    handle: int,
    **kwargs: Any,  # noqa: ANN401
) -> list[Sequence[int]]:
    """
    Given an image of arbitrary size, return the positions of a specific mob
    found within that image.
    :param img: Potentially cropped image based on current character position and
    skill range.
    :param mobs: The mobs to look for.
    :param handle: The client the image is of.
    :return: List of mob positions found in the image.
    """
    return [pos for mob in mobs for pos in mob.get_onscreen_mobs(img, handle, **kwargs)]


def box_center(box: Sequence[int]) -> tuple[float, float]:
    """
    Center point of a detection box, in the x1, y1, x2, y2 format that
    `Character.get_onscreen_position` returns.

    Exists so the on-screen position of the character - a *box* - can be handed
    to `get_closest_mob_direction`, which compares *points*.
    :param box: Rectangle (x1, y1, x2, y2).
    :return: (x, y) center of that rectangle.
    """
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2, (y1 + y2) / 2


def mobs_in_virtual_px(
    mobs: list[Sequence[int]], client_size: tuple[int, int], camera: Camera
) -> list[tuple[float, float]]:
    """
    Where mobs found on screen stand, in virtual px: the middle of each
    detection box's bottom edge, placed through the camera of the frame
    they were found on (`Camera.to_virtual`). Whatever the detections
    found is placed; how good they are is the detectors' business.
    :param mobs: Rectangles (x1, y1, x2, y2) in client px, as
        `get_onscreen_mobs` returns.
    :param client_size: The size of the client they were found on.
    :param camera: The camera of the frame they were found on.
    """
    return [
        camera.to_virtual(((x1 + x2) / 2, y2), client_size) for x1, _, x2, y2 in mobs
    ]


def get_closest_mob_direction(
    character_pos: Sequence[float], mobs: list[Sequence[int]]
) -> str | None:
    """
    Given current character position and list of detected mobs on screen,
    return the (horizontal) direction of the closest mob relative to character.
    :param character_pos: Point (x, y) - use `box_center` on a detection box.
    :param mobs: List of rectangles (x1, y1, x2, y2), as `get_onscreen_mobs` returns.
    :return: Direction of closest mob relative to character, None if no mobs.
    """
    if not mobs:
        return None
    centers = [box_center(rect) for rect in mobs]
    distances = [math.dist(character_pos, center) for center in centers]

    closest_mob_idx = int(np.argmin(distances))
    horizontal_distance = centers[closest_mob_idx][0] - character_pos[0]
    return "left" if horizontal_distance < 0 else "right"
