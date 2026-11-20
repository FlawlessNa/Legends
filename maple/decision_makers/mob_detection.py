"""
Mobs on screen: how many, and where. Plain functions, which `MobsHitting`,
the rotation's sources and `CheckMobsStillSpawn` call; they were
`MobsHittingMixin`'s methods. Which attack reaches them is
`attack_choice`'s.
"""

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


def mob_boxes_in_virtual_px(
    mobs: list[Sequence[int]], client_size: tuple[int, int], camera: Camera
) -> list[tuple[float, float, float, float]]:
    """
    Where mobs found on screen are, in virtual px, as boxes `(left, top, right,
    bottom)`: each detection box's corners placed through the camera of the
    frame they were found on, as `mobs_in_virtual_px` places its feet.
    :param mobs: Rectangles (x1, y1, x2, y2) in client px, as
        `get_onscreen_mobs` returns.
    :param client_size: The size of the client they were found on.
    :param camera: The camera of the frame they were found on.
    """
    boxes = []
    for x1, y1, x2, y2 in mobs:
        left, top = camera.to_virtual((x1, y1), client_size)
        right, bottom = camera.to_virtual((x2, y2), client_size)
        boxes.append((left, top, right, bottom))
    return boxes
