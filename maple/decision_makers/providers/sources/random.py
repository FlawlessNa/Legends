"""
The `random` destination source: random points on the platforms a Path reaches.

A map from `game_data` has no feature cycle, so the destination is a random
point on the map's platforms (`WorldMap.random_point`, platforms weighted by
their width), drawn again once the character is within `ARRIVAL` of it. What
`wander` claims `DESTINATION` with, whatever the profile's rotation.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

from botting.core import Key
from maple.decision_makers.providers.map import WORLD_MAP
from maple.decision_makers.providers.minimap import POSITION

if TYPE_CHECKING:
    from maple.decision_makers.providers.destination import DestinationProvider
    from maple.model.navigation import Point


class RandomSource:
    """
    The current destination until the character is within `ARRIVAL` of it, then
    a new random one on a platform a Path reaches.
    """

    #: What it reads through the Provider: the map and the position.
    needs: ClassVar[tuple[Key[Any], ...]] = (WORLD_MAP, POSITION)

    #: Arrival, in virtual px: 10 minimap px, as it was judged in minimap px
    #: before #398 (16 virtual px each, `mag` 4).
    ARRIVAL = 160.0

    def __init__(self, provider: DestinationProvider) -> None:
        self.provider = provider

    def next(self) -> Point:
        """
        The current destination until the character is within `ARRIVAL` of it,
        then a new random one. An unsure position holds the destination:
        arrival can't be judged from it.
        """
        provider = self.provider
        target = provider.checked_destination()
        reading = provider.position()
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.ARRIVAL:
            return target
        provider.target_reached(position, target)
        destination = provider.random_point()
        provider.store_platform(destination)
        return destination

    def abandon(self) -> Point:
        """A fresh random point on a platform a Path reaches."""
        return self.provider.random_point()
