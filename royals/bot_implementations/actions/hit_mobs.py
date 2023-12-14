import cv2
import math
import numpy as np
from functools import partial
from typing import Generator, Sequence

from botting.core import controller
from botting.utilities import take_screenshot, Box
from royals.models_implementations import RoyalsData


DEBUG = True


# def hit_closest_in_range(data: RoyalsData, skill: "Skill") -> Generator:
def hit_closest_in_range(data: RoyalsData, skill: str) -> Generator:
    while True:
        # if data.character_in_a_ladder:
        #     yield
        # else:
        data.update("current_on_screen_position")
        x, y = data.current_on_screen_position

        region = Box(left=x - 300, right=x + 300, top=y - 50, bottom=y + 125)
        x, y = region.width / 2, region.height / 2
        # TODO - Crop image based on character location and skill range
        cropped_img = take_screenshot(data.handle, region)

        # There may be multiple types of mobs, and multiple mobs of each
        # The goal is to find the closest mob of any type
        mobs_locations = [
            mob.get_onscreen_mobs(cropped_img) for mob in data.current_map.mobs
        ]
        # if all(not mobs for mobs in mobs_locations):
        #     yield
        # else:
        # For each mob type, find the closest, if any
        closest_mobs = []
        for mob in data.current_map.mobs:
            closest_mobs.append(
                _get_closest_mob(
                    (x, y), mobs_locations[data.current_map.mobs.index(mob)]
                )
            )
        closest_mobs = [
            mob for mob in closest_mobs if mob is not None
        ]  # Filter out None values
        closest = None
        if closest_mobs:
            closest = min(closest_mobs, key=lambda mob: math.dist((x, y), mob))
        if DEBUG:
            _debug(cropped_img, (x, y), closest)
        if closest is not None and not data.character_in_a_ladder:
            # Before yielding, we may need to change direction if the mob is not in the same direction as the character
            yield partial(
                cast_skill, data, skill, "left" if x > closest[0] else "right"
            )
        else:
            yield


# async def cast_skill(data: RoyalsData, skill: "Skill", direction: str) -> None:
async def cast_skill(data: RoyalsData, skill: str, direction: str) -> None:
    """
    Casts a skill in a given direction. Updates game status.
    :param data:
    :param skill:
    :param direction:
    :return:
    """
    if direction != data.current_direction:
        await controller.press(
            data.handle, direction, silenced=False, enforce_delay=True
        )
        data.update(current_direction=direction)
    await controller.press(data.handle, skill, silenced=True, cooldown=0.4)


def _get_closest_mob(
    character_position: tuple[float, float], mobs_locations: list[Sequence[int]]
) -> tuple[float, float]:
    """Given a list of mobs locations, returns the location of the closest mob to the character."""
    centers = [
        (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2) for rect in mobs_locations
    ]
    distances = [math.dist(character_position, center) for center in centers]
    if distances:
        min_dist = min(distances)
        min_dist_idx = distances.index(min_dist)
        return centers[min_dist_idx]


def _debug(
    img: np.ndarray, current_pos: tuple[float, float], closest_mob: tuple[float, float]
) -> None:
    if closest_mob is not None:
        x, y = closest_mob
        cv2.circle(img, (int(x), int(y)), 5, (0, 255, 0), -1)
    x, y = current_pos
    cv2.circle(img, (int(x), int(y)), 5, (0, 0, 255), -1)
    cv2.imshow("_DEBUG_ actions.hit_mobs.hit_closest_in_range", img)
    cv2.waitKey(1)
