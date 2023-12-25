import cv2
import math
import numpy as np
import time

from functools import partial
from typing import Sequence, Generator

from botting.core import QueueAction
from botting.models_abstractions import BaseMob
from botting.utilities import take_screenshot, Box
from royals import RoyalsData
from royals.actions import cast_skill
from royals.models_implementations import Skill

DEBUG = True


@QueueAction.action_generator(priority=10)
def hit_mobs(data: RoyalsData, skill: Skill) -> Generator:
    on_screen_pos = None
    last_cast = 0

    while True:
        res = None
        closest_mob_direction = None
        data.update("current_on_screen_position")
        if (
            not data.character_in_a_ladder
            and time.perf_counter() - last_cast >= skill.animation_time
        ):
            # data.update(currently_attacking=False)
            on_screen_pos = (
                data.current_on_screen_position
                if data.current_on_screen_position is not None
                else on_screen_pos
            )
            if on_screen_pos:
                x, y = on_screen_pos
                region = Box(
                    left=x - skill.horizontal_screen_range,
                    right=x + skill.horizontal_screen_range,
                    top=y - skill.vertical_screen_range,
                    bottom=y + skill.vertical_screen_range,
                )
                x, y = region.width / 2, region.height / 2
                cropped_img = take_screenshot(data.handle, region)
                mobs_locations = get_mobs_positions_in_img(
                    cropped_img, data.current_mobs
                )

                if skill.unidirectional:
                    closest_mob_direction = get_closest_mob_direction(
                        (x, y), mobs_locations
                    )

                if DEBUG:
                    _debug(cropped_img, (x, y), mobs_locations)

                if mobs_locations:
                    res = partial(
                        cast_skill, data.handle, data.ign, skill, closest_mob_direction
                    )

        if res is not None:
            last_cast = time.perf_counter()
            data.update(currently_attacking=True)
        else:
            data.update(currently_attacking=False)

        yield res


def mob_count_in_img(img: np.ndarray, mobs: list[BaseMob]) -> int:
    """
    Given an image of arbitrary size, return the mob count of a specific mob found within that image.
    :param img: Potentially cropped image based on current character position and skill range.
    :param mobs: The mobs to look for.
    :return: Total number of mobs detected in the image
    """
    return sum([mob.get_mob_count(img) for mob in mobs])


def get_mobs_positions_in_img(
    img: np.ndarray, mobs: list[BaseMob]
) -> list[Sequence[int]]:
    """
    Given an image of arbitrary size, return the positions of a specific mob found within that image.
    :param img: Potentially cropped image based on current character position and skill range.
    :param mobs: The mobs to look for.
    :return: List of mob positions found in the image.
    """
    return [pos for mob in mobs for pos in mob.get_onscreen_mobs(img)]


def get_closest_mob_direction(
    character_pos: Sequence[float], mobs: list[Sequence[int]]
) -> str | None:
    """
    Given current character position and list of detected mobs on screen,
    return the (horizontal) direction of the closest mob relative to character.
    :param character_pos: Rectangle (x, y, w, h)
    :param mobs: List of rectangles (x, y, w, h)
    :return: Direction of closest mob relative to character.
    """
    if not mobs:
        return None
    centers = [(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2) for rect in mobs]
    distances = [math.dist(character_pos, center) for center in centers]

    # Find minimum distance in terms of absolute value, but retain its sign
    closest_mob_idx = np.argmin(np.abs(distances))
    return "left" if distances[closest_mob_idx] < 0 else "right"


def _debug(
    img: np.ndarray,
    current_pos: tuple[float, float],
    mobs_locations: list[Sequence[int]],
) -> None:
    if mobs_locations:
        for loc in mobs_locations:
            x, y, w, h = loc
            cv2.rectangle(
                img, (int(x), int(y)), (int(x + w), int(y + h)), (255, 255, 255), 2
            )

    x, y = current_pos
    cv2.circle(img, (int(x), int(y)), 5, (0, 0, 255), -1)
    cv2.imshow("_DEBUG_ actions.hit_mobs.hit_closest_in_range", img)
    cv2.waitKey(1)
