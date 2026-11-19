"""
Regression tests for the next_target hijack/reset handoff (issue #48).

A DecisionMaker (a since-removed party rebuff was one) temporarily pins `next_target` to a fixed
point, then hands rotation back to whoever owns it. It used to hand it back by
re-running `_create_rotation_attributes` from its *own* instance, which rebound
the update function to a DecisionMaker that cannot read mobs off the screen -
permanently crashing Rotation on the next update. The reset now restores the
snapshot taken at hijack time, so the owner's bound method comes back intact.

The owner is `DestinationProvider` now (#441), which serves `next_target` as
`DESTINATION`. The legacy hijack (`NextTargetMixin._set_fixed_target`) stays for
unported code and must still hand the Provider's own update back; a ported
DecisionMaker claims `DESTINATION` instead, and a Claim hands it back the same.

Everything is faked at the BotData level: no game client is involved.
"""

from types import MethodType
from typing import cast

import pytest

from botting.core import BotData, fixed
from botting.screen import Reading
from maple.decision_makers.mixins import NextTargetMixin
from maple.decision_makers.providers import DESTINATION, DestinationProvider
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab.fixture_maps import walk_corridor
from tests.test_maple.serving import destination

WORLD = WorldMap.from_map_data(walk_corridor())


class _TargetHijacker(NextTargetMixin):
    """
    Stands in for an unported DecisionMaker that pins the target, then resets
    it. What tells it from the owner is only that it is not the Provider.
    """

    def __init__(self, data: BotData) -> None:
        self.data = data
        self._reset_flag = False


def _here() -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(50.0, 0.0, PositionSource.FUSED), 0.0)


@pytest.fixture
def owner() -> DestinationProvider:
    """The rotation's owner, with smart rotation on."""
    return destination(WORLD, _here, smart_rotation_enabled=True, mob_count_threshold=2)


@pytest.fixture
def basic_owner() -> DestinationProvider:
    """The rotation's owner, with smart rotation off."""
    return destination(WORLD, _here)


def _update_function(data: BotData) -> MethodType:
    return cast(MethodType, data._managed[DESTINATION.name].update_function)  # pyright: ignore[reportPrivateUsage]


# --- smart rotation -----------------------------------------------------------


def test_owner_installs_its_own_smart_rotation_target(
    owner: DestinationProvider,
) -> None:
    update_function = _update_function(owner.data)
    assert update_function.__self__ is owner
    assert update_function.__func__ is DestinationProvider._smart  # pyright: ignore[reportPrivateUsage]


def test_hijack_pins_the_target(owner: DestinationProvider) -> None:
    hijacker = _TargetHijacker(owner.data)
    hijacker._set_fixed_target((1, 2))
    owner.data.update_attribute("next_target")
    assert owner.data.next_target == (1, 2)


def test_reset_restores_the_owners_update_function(
    owner: DestinationProvider,
) -> None:
    hijacker = _TargetHijacker(owner.data)
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()

    update_function = _update_function(owner.data)
    assert update_function.__self__ is owner
    assert update_function.__func__ is DestinationProvider._smart  # pyright: ignore[reportPrivateUsage]


def test_smart_rotation_survives_a_full_hijack_reset_cycle(
    owner: DestinationProvider,
) -> None:
    hijacker = _TargetHijacker(owner.data)
    hijacker._set_fixed_target((1, 2))
    owner.data.update_attribute("next_target")
    hijacker._restore_rotation_target()

    # Used to raise AssertionError: the reset had rebound next_target to the
    # hijacker, which had no `get_mobs_positions_in_img` when it was a mixin's.
    owner.data.update_attribute("next_target")
    assert _update_function(owner.data).__self__ is owner


def test_repeated_hijacks_still_restore_the_owner(owner: DestinationProvider) -> None:
    hijacker = _TargetHijacker(owner.data)
    hijacker._set_fixed_target((1, 2))
    hijacker._set_fixed_target((3, 4))
    hijacker._restore_rotation_target()
    assert _update_function(owner.data).__self__ is owner


def test_reset_without_rotation_attributes_is_a_noop() -> None:
    data = BotData("NoRotation")
    hijacker = _TargetHijacker(data)
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()
    assert not data.is_provided(DESTINATION)


# --- basic rotation -----------------------------------------------------------
# The same handoff, with smart rotation off.


def test_reset_restores_the_random_target_function(
    basic_owner: DestinationProvider,
) -> None:
    hijacker = _TargetHijacker(basic_owner.data)
    hijacker._set_fixed_target((1, 2))
    hijacker._restore_rotation_target()

    update_function = _update_function(basic_owner.data)
    assert update_function.__self__ is basic_owner
    assert update_function.__func__ is DestinationProvider.random_destination


# --- the same handoff, through a Claim ------------------------------------------


@pytest.mark.parametrize("smart", [True, False], ids=["smart", "basic"])
def test_a_claim_hands_the_owners_update_and_target_back(smart: bool) -> None:
    owner = destination(
        WORLD,
        _here,
        smart_rotation_enabled=smart,
        mob_count_threshold=2,
    )
    data = owner.data
    before, own = data.next_target, _update_function(data)

    claim = data.claim(DESTINATION, fixed((1.0, 2.0)), holder="X(T)", reason="test")
    data.update_attribute("next_target")
    assert data.next_target == (1.0, 2.0)
    data.release(claim)

    assert data.next_target == before
    assert _update_function(data) == own
    data.update_attribute("next_target")  # the owner's own mode runs again
