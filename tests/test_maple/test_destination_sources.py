"""
Destination sources (#577): each rotation is a source registered by name in
`maple/decision_makers/providers/destination.py`, and `DestinationProvider`
serves the one the profile's rotation names. The Provider's `needs` is every
registered source's.

Faked at the BotData level: no game client is involved. The Provider is built
as assembly builds it (`serving.destination`).
"""

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from botting.core import Key, StartupRefused
from botting.screen import Reading
from maple.decision_makers import rotation_setting
from maple.decision_makers.providers import (
    DESTINATION,
    MAP_ID,
    DestinationProvider,
    wander,
)
from maple.decision_makers.providers import destination as destination_module
from maple.decision_makers.providers.destination import SOURCES, register_source
from maple.decision_makers.providers.map import WORLD_MAP
from maple.decision_makers.providers.minimap import POSITION
from maple.decision_makers.providers.sources.random import RandomSource
from maple.decision_makers.providers.sources.smart import SmartSource
from maple.decision_makers.rotation_setting import ROTATIONS
from maple.model.navigation import Point
from maple.model.world import WorldMap
from maple.screen.position import PositionSource, VirtualPosition
from tests.test_maple.movement_lab.fixture_maps import walk_corridor
from tests.test_maple.serving import destination

#: One floor from x 0 to 700.
WORLD = WorldMap.from_map_data(walk_corridor())
#: Where the test source heads, and where its Abandon goes: on the floor.
SPOT = (42.0, 0.0)
ELSEWHERE = (600.0, -20.0)


def _here() -> Reading[VirtualPosition]:
    return Reading.read(VirtualPosition(50.0, 0.0, PositionSource.FUSED), 0.0)


class _Spot:
    """A source that always heads for `SPOT`, and reads the map's id to do so."""

    needs: ClassVar[tuple[Key[Any], ...]] = (MAP_ID,)

    def __init__(self, provider: DestinationProvider) -> None:
        self.provider = provider
        self.abandoned = 0

    def next(self) -> Point:
        self.provider.read(MAP_ID)  # refused unless the Provider needs it
        return SPOT

    def abandon(self) -> Point:
        self.abandoned += 1
        return ELSEWHERE


@pytest.fixture
def spot(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """
    Registers `_Spot` as the `spot` rotation, as a new rotation is added: a name
    in `ROTATIONS` and a line in the registry. Undone after the test.
    """
    monkeypatch.setattr(rotation_setting, "ROTATIONS", (*ROTATIONS, "spot"))
    monkeypatch.setattr(destination_module, "SOURCES", dict(SOURCES))
    monkeypatch.setattr(DestinationProvider, "needs", DestinationProvider.needs)
    return lambda: register_source("spot", _Spot)


# --- the registry --------------------------------------------------------------


def test_every_registered_source_is_a_rotation() -> None:
    assert set(SOURCES) <= set(ROTATIONS)


def test_random_and_smart_are_registered_sources() -> None:
    assert SOURCES["random"] is RandomSource
    assert SOURCES["smart"] is SmartSource


def test_the_providers_needs_are_every_registered_sources() -> None:
    sources = {key for source in SOURCES.values() for key in source.needs}

    assert set(DestinationProvider.needs) == sources | {WORLD_MAP, POSITION}
    assert len(DestinationProvider.needs) == len(set(DestinationProvider.needs))


def test_the_hunting_area_refuses_the_start_until_its_source_is_built() -> None:
    """#579 registers it; until then, naming it is refused at assembly."""
    assert "hunting_area" not in SOURCES

    with pytest.raises(StartupRefused, match="hunting_area.*not built yet"):
        destination(WORLD, _here, rotation="hunting_area")


def test_settings_the_setting_refuses_refuse_the_start() -> None:
    with pytest.raises(StartupRefused, match="smart_rotation_enabled"):
        destination(WORLD, _here, rotation="random", smart_rotation_enabled=False)


# --- the source served -----------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "served"),
    [
        ({}, RandomSource),
        ({"smart_rotation_enabled": False}, RandomSource),
        ({"smart_rotation_enabled": True, "mob_count_threshold": 2}, SmartSource),
        ({"rotation": "random"}, RandomSource),
        ({"rotation": "smart", "mob_count_threshold": 2}, SmartSource),
    ],
    ids=["neither", "smart-off", "smart-on", "random", "smart"],
)
def test_the_provider_serves_the_source_the_settings_name(
    settings: dict[str, Any], served: type
) -> None:
    provider = destination(WORLD, _here, **settings)

    assert type(provider.source) is served


def test_smart_with_no_mob_count_threshold_refuses_the_start() -> None:
    with pytest.raises(StartupRefused, match="mob_count_threshold"):
        destination(WORLD, _here, rotation="smart")


def test_a_registered_source_is_served_when_the_settings_name_it(
    spot: Callable[[], None],
) -> None:
    spot()

    provider = destination(WORLD, _here, rotation="spot")
    provider.data.update_attribute(DESTINATION.name)

    assert isinstance(provider.source, _Spot)
    assert provider.data.read(DESTINATION) == SPOT
    assert MAP_ID in DestinationProvider.needs


def test_a_new_rotation_must_be_in_rotations(
    spot: Callable[[], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    spot()
    monkeypatch.setattr(rotation_setting, "ROTATIONS", ROTATIONS)  # name left out

    with pytest.raises(StartupRefused, match="`rotation: spot` is not a rotation"):
        destination(WORLD, _here, rotation="spot")


# --- Abandon, and the Claim's wander ---------------------------------------------


def test_abandon_takes_the_served_sources_new_destination(
    spot: Callable[[], None],
) -> None:
    spot()
    provider = destination(WORLD, _here, rotation="spot")
    assert isinstance(provider.source, _Spot)

    assert provider.abandon() == ELSEWHERE
    assert provider.data.read(DESTINATION) == ELSEWHERE
    assert provider.source.abandoned == 1


def test_abandon_asks_the_source_nothing_while_the_destination_is_claimed(
    spot: Callable[[], None],
) -> None:
    spot()
    provider = destination(WORLD, _here, rotation="spot")
    assert isinstance(provider.source, _Spot)
    provider.data.claim(
        DESTINATION, lambda _: (300.0, 0.0), holder="Claimant(T)", reason="test"
    )

    assert provider.abandon() is None
    assert provider.source.abandoned == 0
    assert provider.data.read(DESTINATION) == (300.0, 0.0)


def test_a_wander_claim_serves_the_random_source_whatever_the_rotation(
    spot: Callable[[], None],
) -> None:
    spot()
    provider = destination(WORLD, _here, rotation="spot")
    provider.data.update_attribute(DESTINATION.name)
    assert provider.data.read(DESTINATION) == SPOT  # within arrival of `_here`

    # Taking the Claim refreshes it once: the random source judges SPOT reached.
    provider.data.claim(DESTINATION, wander, holder="X(T)", reason="test")

    assert isinstance(provider.wanderer, RandomSource)
    assert provider.data.read(DESTINATION) != SPOT
    assert WORLD.platform_at(provider.data.read(DESTINATION)) is not None
