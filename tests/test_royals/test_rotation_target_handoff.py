"""
Regression tests for the next_target hijack/reset handoff (issue #48).

A DecisionMaker such as PartyRebuff temporarily pins `next_target` to a fixed
point, then hands rotation back to whoever owns it. It used to hand it back by
re-running `_create_rotation_attributes` from its *own* instance, which rebound
the update function to a DecisionMaker that cannot read mobs off the screen -
permanently crashing Rotation on the next update. The reset now restores the
snapshot taken at hijack time, so the owner's bound method comes back intact.

Everything is faked at the BotData level: no game client is involved.
"""

import unittest

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
    Stands in for PartyRebuff: pins the target, then resets it. Deliberately does
    *not* inherit MobsHittingMixin - that is what made the old reset fatal.
    """

    def __init__(self, data: BotData) -> None:
        self.data = data
        self._reset_flag = False


class TestRotationTargetHandoff(unittest.TestCase):
    def setUp(self):
        self.data = BotData("TestBot")
        self.data.set_static("current_minimap", _FakeMinimap())
        self.data.set_static("current_minimap_position", (50, 50))

        self.owner = _RotationOwner(self.data)
        self.owner._create_rotation_attributes(
            smart_rotation=True, mob_count_threshold=2
        )
        self.hijacker = _TargetHijacker(self.data)

    def _update_function(self):
        return self.data._managed["next_target"].update_function

    def test_owner_installs_its_own_smart_rotation_target(self):
        self.assertTrue(self.data.has_smart_rotation)
        self.assertIs(self._update_function().__self__, self.owner)

    def test_hijack_pins_the_target(self):
        self.hijacker._set_fixed_target((1, 2))
        self.data.update_attribute("next_target")
        self.assertEqual(self.data.next_target, (1, 2))

    def test_reset_restores_the_owners_update_function(self):
        self.hijacker._set_fixed_target((1, 2))
        self.hijacker._restore_rotation_target()

        update_function = self._update_function()
        self.assertIs(update_function.__self__, self.owner)
        self.assertIs(update_function.__func__, _RotationOwner._smart_rotation_target)

    def test_smart_rotation_survives_a_full_hijack_reset_cycle(self):
        self.hijacker._set_fixed_target((1, 2))
        self.data.update_attribute("next_target")
        self.hijacker._restore_rotation_target()

        # Used to raise AssertionError: the reset had rebound next_target to the
        # hijacker, which has no `get_mobs_positions_in_img`.
        self.data.update_attribute("next_target")
        self.assertTrue(self.data.has_smart_rotation)

    def test_repeated_hijacks_still_restore_the_owner(self):
        self.hijacker._set_fixed_target((1, 2))
        self.hijacker._set_fixed_target((3, 4))
        self.hijacker._restore_rotation_target()
        self.assertIs(self._update_function().__self__, self.owner)

    def test_reset_without_rotation_attributes_is_a_noop(self):
        data = BotData("NoRotation")
        hijacker = _TargetHijacker(data)
        hijacker._set_fixed_target((1, 2))
        hijacker._restore_rotation_target()
        self.assertFalse(data.has_rotation_attributes)


class TestBasicRotationTargetHandoff(unittest.TestCase):
    """The same handoff, with smart rotation off."""

    def setUp(self):
        self.data = BotData("TestBot")
        self.data.set_static("current_minimap", _FakeMinimap())
        self.data.set_static("current_minimap_position", (50, 50))

        self.owner = _RotationOwner(self.data)
        self.owner._create_rotation_attributes()
        self.hijacker = _TargetHijacker(self.data)

    def test_reset_restores_the_random_target_function(self):
        self.hijacker._set_fixed_target((1, 2))
        self.hijacker._restore_rotation_target()

        update_function = self.data._managed["next_target"].update_function
        self.assertIs(update_function.__self__, self.owner)
        self.assertIs(
            update_function.__func__, _RotationOwner._update_next_random_target
        )


if __name__ == "__main__":
    unittest.main()
