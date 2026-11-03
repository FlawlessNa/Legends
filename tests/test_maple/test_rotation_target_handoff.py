"""
Regression tests for the next_target hijack/reset handoff (issue #48).

A DecisionMaker (a since-removed party rebuff was one) temporarily pins `next_target` to a fixed
point, then hands rotation back to whoever owns it. It used to hand it back by
re-running `_create_rotation_attributes` from its *own* instance, which rebound
the update function to a DecisionMaker that cannot read mobs off the screen -
permanently crashing Rotation on the next update. The reset now restores the
snapshot taken at hijack time, so the owner's bound method comes back intact.

Everything is faked at the BotData level: no game client is involved.
"""

from types import MethodType
from typing import cast

import pytest

from botting.core import BotData
from maple.decision_makers.mixins import MobsHittingMixin, NextTargetMixin


class _FakeFeature:
    left = 0
    right = 100
    top = 5
    avoid_edges = False
    edge_threshold = 0

    def random(self) -> tuple[int, int]:
        return 5, 5


class _FakeMinimap:
    """The bare minimum `_create_rotation_attributes` reads off a minimap."""

    feature_cycle = None

    def random_point(self) -> tuple[int, int]:
        return 5, 5

    def get_feature_containing(self, target: tuple[int, int]) -> _FakeFeature:
        return _FakeFeature()


class _RotationOwner(MobsHittingMixin, NextTargetMixin):
    """Stands in for the Rotation DecisionMaker: owns the smart-rotation target."""

    def __init__(self, data: BotData) -> None:
        self.data = data


class _TargetHijacker(NextTargetMixin):
    """
    Stands in for a DecisionMaker that pins the target, then resets it. Deliberately does
    *not* inherit MobsHittingMixin - that is what made the old reset fatal.
    """

    def __init__(self, data: BotData) -> None:
        self.data = data
        self._reset_flag = False


@pytest.fixture
def data() -> BotData:
    data = BotData("TestBot")
    data.set_static("current_minimap", _FakeMinimap())
    data.set_static("current_minimap_position", (50, 50))
    return data


@pytest.fixture
def owner(data: BotData) -> _RotationOwner:
    """The rotation owner, with smart rotation on."""
    owner = _RotationOwner(data)
    owner._create_rotation_attributes(smart_rotation=True, mob_count_threshold=2)
    return owner


@pytest.fixture
def basic_owner(data: BotData) -> _RotationOwner:
    """The rotation owner, with smart rotation off."""
    owner = _RotationOwner(data)
    owner._create_rotation_attributes()
    return owner


@pytest.fixture
def hijacker(data: BotData) -> _TargetHijacker:
    return _TargetHijacker(data)


def _update_function(data: BotData) -> MethodType:
    return cast(MethodType, data._managed["next_target"].update_function)


# --- smart rotation -----------------------------------------------------------


def test_owner_installs_its_own_smart_rotation_target(
    data: BotData, owner: _RotationOwner
) -> None:
    assert data.has_smart_rotation
    assert _update_function(data).__self__ is owner


def test_hijack_pins_the_target(
    data: BotData, owner: _RotationOwner, hijacker: _TargetHijacker
) -> None:
    hijacker._set_fixed_target((1, 2))
    data.update_attribute("next_target")
    assert data.next_target == (1, 2)


def test_reset_restores_the_owners_update_function(
    data: BotData, owner: _RotationOwner, hijacker: _TargetHijacker
) -> None:
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()

    update_function = _update_function(data)
    assert update_function.__self__ is owner
    assert update_function.__func__ is _RotationOwner._smart_rotation_target


def test_smart_rotation_survives_a_full_hijack_reset_cycle(
    data: BotData, owner: _RotationOwner, hijacker: _TargetHijacker
) -> None:
    hijacker._set_fixed_target((1, 2))
    data.update_attribute("next_target")
    hijacker._restore_rotation_target()

    # Used to raise AssertionError: the reset had rebound next_target to the
    # hijacker, which has no `get_mobs_positions_in_img`.
    data.update_attribute("next_target")
    assert data.has_smart_rotation


def test_repeated_hijacks_still_restore_the_owner(
    data: BotData, owner: _RotationOwner, hijacker: _TargetHijacker
) -> None:
    hijacker._set_fixed_target((1, 2))
    hijacker._set_fixed_target((3, 4))
    hijacker._restore_rotation_target()
    assert _update_function(data).__self__ is owner


def test_reset_without_rotation_attributes_is_a_noop() -> None:
    data = BotData("NoRotation")
    hijacker = _TargetHijacker(data)
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()
    assert not data.has_rotation_attributes


# --- basic rotation -----------------------------------------------------------
# The same handoff, with smart rotation off.


def test_reset_restores_the_random_target_function(
    data: BotData, basic_owner: _RotationOwner, hijacker: _TargetHijacker
) -> None:
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()

    update_function = _update_function(data)
    assert update_function.__self__ is basic_owner
    assert update_function.__func__ is _RotationOwner._update_next_random_target
