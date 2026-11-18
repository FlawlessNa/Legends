"""
`_smart_rotation_target` reads mob rectangles as x1, y1, x2, y2 (issue #74), and
places them in virtual px through the camera of the frame they were found on
(#398), on the platform of the target.

Faked at the BotData level, with the mobs stubbed: no game client is involved.
The owner below is declared here with the same shape as `_RotationOwner` in
`test_rotation_target_handoff.py`, rather than imported from it.
"""

from collections.abc import Sequence
from types import SimpleNamespace

import numpy as np
import pytest

from botting.core import BotData
from botting.screen import Frame, Reading
from maple.decision_makers.mixins import MobsHittingMixin, NextTargetMixin
from maple.model.world import WorldMap
from maple.screen.position import Camera, PositionSource, VirtualPosition
from tests.test_maple.movement_lab.fixture_maps import walk_corridor

#: One floor from x 0 to 700: flat at y 0 to x 300, a slope up to y -20 at x 400,
#: then flat again.
WORLD = WorldMap.from_map_data(walk_corridor())
CLIENT = (1000, 600)
#: The play area drawn 1:1 with its top-left at (0, -300): a client x is a virtual x.
ORIGIN = Camera(0, -300, 1.0, 2.0, CLIENT)
TWO_LEFT = [(70, 40, 90, 70), (60, 40, 80, 70)]


class _Owner(MobsHittingMixin, NextTargetMixin):
    TIME_ON_TARGET = 0.0

    def __init__(self, data: BotData, mobs: list[tuple[int, int, int, int]]) -> None:
        self.data = data
        self._mobs = mobs

    def get_mobs_positions_in_img(
        self, *args: object, **kwargs: object
    ) -> list[Sequence[int]]:
        return list(self._mobs)


def _target(
    mobs: list[tuple[int, int, int, int]],
    *,
    here: tuple[float, float] = (100.0, 0.0),
    camera: Camera | None = ORIGIN,
) -> tuple[float, float]:
    """
    The target smart rotation picks once on target at `here`, with `mobs` found
    on a frame whose camera is `camera` (`None`: that read matched no camera).
    """
    data = BotData("TestBot")
    data.set_static("world_map", WORLD)
    position = Reading.read(VirtualPosition(*here, PositionSource.FUSED), 0.0)
    data.create_attribute("current_position", lambda: position)
    data.set_static("position_fusion", SimpleNamespace(camera=camera))
    image = Frame(np.zeros((600, 1000, 3), np.uint8), CLIENT, 0.0, True, True)
    data.create_attribute("current_frame", lambda: image, initial_value=image)
    data.set_static("current_mobs", ())
    # The character's box on screen, x1, y1, x2, y2: the mask is built around it.
    character = (90, 40, 110, 70)
    data.create_attribute(
        "current_on_screen_position", lambda: character, initial_value=character
    )
    owner = _Owner(data, mobs)
    owner._create_rotation_attributes(smart_rotation=True, mob_count_threshold=2)
    data.next_target = here
    # Skip the "already on target" gate and the wait on it.
    owner._first_time_on_target = False
    owner._last_target_reached_at = 0.0
    return owner._smart_rotation_target()


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

    assert (target[0] < 100.0) == (expected_side == "left")
    assert target[1] == 0.0  # on the floor


def test_the_step_is_the_mobs_mean_distance_on_the_target_platform() -> None:
    """Centres 80 and 70: 20 and 30 px left of the character, so 25 px."""
    assert _target(TWO_LEFT) == pytest.approx((75.0, 0.0))


def test_the_mobs_are_placed_through_the_camera() -> None:
    """
    The camera at x 200 puts the same boxes 200 px further right on the map: from
    a character at 300 they are as far left as they were from one at 100.
    """
    target = _target(
        TWO_LEFT, here=(300.0, 0.0), camera=Camera(200, -300, 1.0, 2.0, CLIENT)
    )

    assert target == pytest.approx((275.0, 0.0))


def test_a_scaled_play_area_scales_the_mobs_distance() -> None:
    """The client drawn at twice its play area: 50 client px are 25 virtual px."""
    target = _target(
        [(40, 40, 60, 70), (40, 40, 60, 70)],
        camera=Camera(50, -300, 1.0, 2.0, (500, 300)),
    )

    assert target == pytest.approx((75.0, 0.0))


def test_the_step_is_capped_and_follows_the_slope() -> None:
    """Mobs 400 px left step 160 px (10 minimap px), to the slope's height there."""
    target = _target([(90, 40, 110, 70), (90, 40, 110, 70)], here=(500.0, -20.0))

    assert target[0] == pytest.approx(340.0)
    assert target[1] == pytest.approx(-8.0)
    assert WORLD.platform_at(target) == WORLD.platforms[0]


def test_without_a_camera_the_target_is_a_point_on_the_same_platform() -> None:
    """No camera on that frame: nothing places the mobs, so no step towards them."""
    target = _target(TWO_LEFT, camera=None)

    assert WORLD.platform_at(target) == WORLD.platforms[0]
