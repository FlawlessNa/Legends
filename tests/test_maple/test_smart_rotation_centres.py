"""
`_smart_rotation_target` reads mob rectangles as x1, y1, x2, y2 (issue #74), the
same shape `MobsHittingMixin.box_center` reads, so the two cannot drift apart.

Faked at the BotData level, with the mobs stubbed: no game client is involved.
"""

from collections.abc import Sequence

import numpy as np
import pytest

from botting.core import BotData
from maple.decision_makers.mixins import MobsHittingMixin, NextTargetMixin


class _Feature:
    left = 0
    right = 100
    top = 5
    avoid_edges = False
    edge_threshold = 0


class _Minimap:
    feature_cycle = None
    map_area_width = 100

    def random_point(self) -> tuple[int, int]:
        return 50, 50

    def get_feature_containing(self, target: tuple[int, int]) -> _Feature:
        return _Feature()


class _Map:
    vr_width = 100


class _Owner(MobsHittingMixin, NextTargetMixin):
    TIME_ON_TARGET = 0.0

    def __init__(self, data: BotData, mobs: list[tuple[int, int, int, int]]) -> None:
        self.data = data
        self._mobs = mobs

    def get_mobs_positions_in_img(
        self, *args: object, **kwargs: object
    ) -> list[Sequence[int]]:
        return list(self._mobs)


def _target(mobs: list[tuple[int, int, int, int]]) -> tuple[int, int]:
    data = BotData("TestBot")
    data.set_static("current_minimap", _Minimap())
    data.set_static("current_map", _Map())
    data.set_static("current_minimap_position", (50, 50))
    image = np.zeros((600, 1000, 3), np.uint8)
    data.create_attribute("current_client_img", lambda: image, initial_value=image)
    data.set_static("current_mobs", ())
    # The character, x1, y1, x2, y2: centred at x 100.
    character = (90, 40, 110, 70)
    data.create_attribute(
        "current_on_screen_position", lambda: character, initial_value=character
    )
    owner = _Owner(data, mobs)
    owner._create_rotation_attributes(smart_rotation=True, mob_count_threshold=2)
    # Skip the "already on target" gate and the wait on it.
    owner._first_time_on_target = False
    owner._last_target_reached_at = 0.0
    return owner._smart_rotation_target()  # pyright: ignore[reportReturnType]


@pytest.mark.parametrize(
    ("mobs", "expected_side"),
    [
        # Two left, one right. (70, 40, 90, 70) has centre 80: left. Misread as
        # x, y, w, h it would be 115, and the majority would flip right.
        ([(70, 40, 90, 70), (60, 40, 80, 70), (130, 40, 150, 70)], "left"),
        ([(130, 40, 150, 70), (140, 40, 160, 70), (70, 40, 90, 70)], "right"),
    ],
)
def test_the_target_goes_to_the_side_with_more_mobs(
    mobs: list[tuple[int, int, int, int]], expected_side: str
) -> None:
    target = _target(mobs)
    minimap_x = 50
    assert (target[0] < minimap_x) == (expected_side == "left")
