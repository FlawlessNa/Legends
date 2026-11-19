"""
Regression tests for the rotation target's handoff (issue #48).

A DecisionMaker (a since-removed party rebuff was one) temporarily pins the
rotation's target to a fixed point, then hands rotation back to whoever owns
it. It used to hand it back by re-running `_create_rotation_attributes` from its
*own* instance, which rebound the update function to a DecisionMaker that
cannot read mobs off the screen - permanently crashing Rotation on the next
update.

The owner is `DestinationProvider` now (#441), which serves the target as
`DESTINATION`. A DecisionMaker pins it with a Claim, whose release hands the
Provider's own update back intact (the legacy hijack, `NextTargetMixin`, went
with the mixins, #444).

Everything is faked at the BotData level: no game client is involved.
"""

from types import MethodType
from typing import cast

import pytest

from botting.core import BotData, fixed
from botting.screen import Reading
from maple.decision_makers.providers import DESTINATION, DestinationProvider
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab.fixture_maps import walk_corridor
from tests.test_maple.serving import destination

WORLD = WorldMap.from_map_data(walk_corridor())


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
    before, own = data.read(DESTINATION), _update_function(data)

    claim = data.claim(DESTINATION, fixed((1.0, 2.0)), holder="X(T)", reason="test")
    data.refresh(DESTINATION)
    assert data.read(DESTINATION) == (1.0, 2.0)
    data.release(claim)

    assert data.read(DESTINATION) == before
    assert _update_function(data) == own
    data.refresh(DESTINATION)  # the owner's own mode runs again
