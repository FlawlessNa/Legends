"""
Regression tests for the unidirectional training-skill path (issue #51).

`MobsHitting._decide` used to reach for `(x, y)` - two names that were never
bound - the first time a unidirectional skill passed the mob threshold, so the
branch could only ever raise `NameError`, right after a `breakpoint()` froze the
bot. The facing is now derived from the character's on-screen bounding box.

Everything here is pure geometry: the detection call is stubbed, so no game
client and no `MobsHitting` instance are involved.
"""

import logging

import pytest

from maple.decision_makers.mixins import MobsHittingMixin
from maple.decision_makers.mobs_hitting import MobsHitting

# A character standing at x = 100, y = 55 on screen: x1, y1, x2, y2.
CHARACTER_BOX = (90, 40, 110, 70)

# Mob rectangles, in the x, y, w, h shape `get_onscreen_mobs` returns.
MOB_FAR_LEFT = (0, 40, 20, 30)
MOB_NEAR_LEFT = (60, 40, 20, 30)
MOB_NEAR_RIGHT = (130, 40, 20, 30)
MOB_FAR_RIGHT = (400, 40, 20, 30)


class _FakeBotData:
    """The two reads `_closest_mob_direction` makes before the detection call."""

    current_client_img = None
    current_mobs = ()


class _FakeMobsHitting(MobsHittingMixin):
    """
    The slice of `MobsHitting` that `_closest_mob_direction` reaches through.

    `_closest_mob_direction` is called unbound against this, which is the point of
    extracting it: the only thing standing between it and pure logic is the one
    detection call stubbed out below.
    """

    def __init__(self, mobs, raises: Exception = None) -> None:
        self._mobs = mobs
        self._raises = raises
        self.data = _FakeBotData()  # only ever forwarded to the stub below

    def get_mobs_positions_in_img(self, *args, **kwargs) -> list:
        if self._raises is not None:
            raise self._raises
        return self._mobs


def _direction(mobs, raises: Exception = None) -> str | None:
    fake = _FakeMobsHitting(mobs, raises)
    return MobsHitting._closest_mob_direction(fake, CHARACTER_BOX, mask=None)


# --- box_center -------------------------------------------------------------


def test_box_center_is_the_middle_of_an_x1y1x2y2_box():
    assert MobsHittingMixin.box_center(CHARACTER_BOX) == (100.0, 55.0)


# --- get_closest_mob_direction ----------------------------------------------


@pytest.mark.parametrize(
    "mobs, expected",
    [
        ([MOB_NEAR_LEFT], "left"),
        ([MOB_NEAR_RIGHT], "right"),
        ([MOB_FAR_LEFT, MOB_NEAR_RIGHT], "right"),
        ([MOB_NEAR_LEFT, MOB_FAR_RIGHT], "left"),
    ],
)
def test_direction_points_at_the_closest_mob(mobs, expected):
    assert (
        MobsHittingMixin.get_closest_mob_direction(
            MobsHittingMixin.box_center(CHARACTER_BOX), mobs
        )
        == expected
    )


def test_direction_is_none_without_mobs():
    assert (
        MobsHittingMixin.get_closest_mob_direction(
            MobsHittingMixin.box_center(CHARACTER_BOX), []
        )
        is None
    )


# --- the unidirectional branch of _decide -----------------------------------


def test_unidirectional_branch_derives_a_facing_from_the_on_screen_box():
    """The branch that used to raise `NameError` on `(x, y)`."""
    assert _direction([MOB_FAR_LEFT, MOB_NEAR_RIGHT]) == "right"
    assert _direction([MOB_NEAR_LEFT, MOB_FAR_RIGHT]) == "left"


def test_unidirectional_branch_returns_none_when_nothing_is_detected():
    assert _direction([]) is None


def test_detection_failure_logs_and_falls_back_to_no_facing(caplog):
    """
    A failed detection must not lose the cast - and must not open a debugger.
    """
    with caplog.at_level(logging.ERROR):
        assert _direction([], raises=RuntimeError("detection blew up")) is None

    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert any("detection blew up" in record.exc_text for record in caplog.records)
