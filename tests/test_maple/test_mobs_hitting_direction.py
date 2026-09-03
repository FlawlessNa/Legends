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
from collections.abc import Sequence

import numpy as np
import pytest

from botting.core import BotData
from maple.decision_makers.mixins import MobsHittingMixin
from maple.decision_makers.mobs_hitting import MobsHitting

# A character standing at x = 100, y = 55 on screen: x1, y1, x2, y2.
CHARACTER_BOX = (90, 40, 110, 70)

# Mob rectangles, in the x, y, w, h shape `get_onscreen_mobs` returns.
MOB_FAR_LEFT = (0, 40, 20, 30)
MOB_NEAR_LEFT = (60, 40, 20, 30)
MOB_NEAR_RIGHT = (130, 40, 20, 30)
MOB_FAR_RIGHT = (400, 40, 20, 30)

# The skill's on-screen mask. `_closest_mob_direction` only forwards it to the
# detection call, stubbed out below, so nothing ever reads its contents.
MASK = np.zeros((1, 1), dtype=np.uint8)


def _fake_data() -> BotData:
    """The two reads `_closest_mob_direction` makes before the detection call."""
    data = BotData("TestBot")
    data.set_static("current_client_img", None)
    data.set_static("current_mobs", ())
    return data


class _FakeMobsHitting(MobsHittingMixin):
    """
    The slice of `MobsHitting` that `_closest_mob_direction` reaches through.

    `_closest_mob_direction` is called unbound against this, which is the point of
    extracting it: the only thing standing between it and pure logic is the one
    detection call stubbed out below.
    """

    def __init__(
        self, mobs: list[Sequence[int]], raises: Exception | None = None
    ) -> None:
        self._mobs = mobs
        self._raises = raises
        self.data = _fake_data()  # only ever forwarded to the stub below

    def get_mobs_positions_in_img(
        self, *args: object, **kwargs: object
    ) -> list[Sequence[int]]:
        if self._raises is not None:
            raise self._raises
        return self._mobs


def _direction(
    mobs: list[Sequence[int]], raises: Exception | None = None
) -> str | None:
    fake = _FakeMobsHitting(mobs, raises)
    # `_closest_mob_direction` is nominally typed to `MobsHitting`, a DecisionMaker
    # whose construction needs a live manager, pipe and proxy factory. Calling it
    # unbound against the stand-in is the whole point of extracting it, so the shape
    # rejecting the argument is the base class's, out of reach from this file.
    return MobsHitting._closest_mob_direction(
        fake,  # pyright: ignore[reportArgumentType]
        CHARACTER_BOX,
        mask=MASK,
    )


# --- box_center -------------------------------------------------------------


def test_box_center_is_the_middle_of_an_x1y1x2y2_box() -> None:
    assert MobsHittingMixin.box_center(CHARACTER_BOX) == (100.0, 55.0)


# --- get_closest_mob_direction ----------------------------------------------


@pytest.mark.parametrize(
    ("mobs", "expected"),
    [
        ([MOB_NEAR_LEFT], "left"),
        ([MOB_NEAR_RIGHT], "right"),
        ([MOB_FAR_LEFT, MOB_NEAR_RIGHT], "right"),
        ([MOB_NEAR_LEFT, MOB_FAR_RIGHT], "left"),
    ],
)
def test_direction_points_at_the_closest_mob(
    mobs: list[Sequence[int]], expected: str
) -> None:
    assert (
        MobsHittingMixin.get_closest_mob_direction(
            MobsHittingMixin.box_center(CHARACTER_BOX), mobs
        )
        == expected
    )


def test_direction_is_none_without_mobs() -> None:
    assert (
        MobsHittingMixin.get_closest_mob_direction(
            MobsHittingMixin.box_center(CHARACTER_BOX), []
        )
        is None
    )


# --- the unidirectional branch of _decide -----------------------------------


def test_unidirectional_branch_derives_a_facing_from_the_on_screen_box() -> None:
    """The branch that used to raise `NameError` on `(x, y)`."""
    assert _direction([MOB_FAR_LEFT, MOB_NEAR_RIGHT]) == "right"
    assert _direction([MOB_NEAR_LEFT, MOB_FAR_RIGHT]) == "left"


def test_unidirectional_branch_returns_none_when_nothing_is_detected() -> None:
    assert _direction([]) is None


def test_detection_failure_logs_and_falls_back_to_no_facing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    A failed detection must not lose the cast - and must not open a debugger.
    """
    with caplog.at_level(logging.ERROR):
        assert _direction([], raises=RuntimeError("detection blew up")) is None

    assert any(record.levelno == logging.ERROR for record in caplog.records)
    assert any(
        "detection blew up" in (record.exc_text or "") for record in caplog.records
    )
