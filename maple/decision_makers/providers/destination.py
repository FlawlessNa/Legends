"""
The rotation's destination: where the character heads next, in virtual px on
the Bot's `WorldMap`, and the platform it is on (#398).

`DestinationProvider` serves the **destination source** the profile's `rotation`
names (`maple/decision_makers/rotation_setting.py`), and movement recovery's
Abandon (#441). `DESTINATION` is the first steerable Data Key: a DecisionMaker
that must send the character somewhere else claims it (`CheckMobsStillSpawn`
wanders, `TrialRunner` walks its schedule), and the Provider's own value comes
back when the Claim is released.

**The sources.** Each rotation is a `DestinationSource`, one module each under
`sources/`, registered by name in `SOURCES` below: `random`, random points on
the platforms (`sources/random.py`), `smart`, towards the mobs
(`sources/smart.py`), and `hunting_area`, towards the mobs inside the Hunting
Area (`sources/hunting_area.py`). The Provider holds no rotation of its own: it builds the
source the profile names, serves its `next()`, and hands Abandon to its
`abandon()`. Its `needs` is every registered source's, so adding a rotation is
one module, one `register_source` line here and one name in `ROTATIONS`.
Custom rotation patterns are a later epic.

**Only platforms a Path reaches.** The sources draw through the Provider
(`random_point`), on the platforms the foothold graph reaches from the
character's position, when the graph and a position are known
(`PathingProvider.reachable_platforms`): some maps have platforms nothing
reaches (on Damp Forest, 7 of its 11, 37 % of their width, from its widest
platform), and a destination there is one no Path joins, which only movement
recovery would ever drop. One drawn before then is checked, and drawn again,
once they are known (`checked_destination`).
"""

import logging
from typing import Any, ClassVar, Protocol

from botting import PARENT_LOG
from botting.core import Key, Provider, StartupRefused
from botting.screen import Reading
from maple.decision_makers.rotation_setting import rotation_name
from maple.launchers.profile import ProfileError
from maple.model.navigation import Point
from maple.model.world import Platform, WorldMap
from maple.screen.position import VirtualPosition, marker_of_feet
from maple.telemetry_events import MOVEMENT_TARGET_REACHED, target_reached_payload

from .map import WORLD_MAP
from .minimap import position_or_unsure
from .sources.hunting_area import AreaWanderSource, HuntingAreaSource
from .sources.random import RandomSource
from .sources.smart import SmartSource

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class DestinationSource(Protocol):
    """
    One rotation: where the character heads. Built with the Provider, which it
    reads and emits through; it decides where to go, never how.

    The source a Claim on `DESTINATION` takes is one too: `wander` serves the
    `random` source's `next()`, and `wander_in_area` an `AreaWanderSource`'s.
    """

    #: The Data Keys it reads, through the Provider. The Provider's `needs` is
    #: every registered source's.
    needs: ClassVar[tuple[Key[Any], ...]]

    def __init__(self, provider: DestinationProvider) -> None:
        """
        No I/O. Built in the Provider's `setup()`.
        :raises StartupRefused: The profile lacks a setting the source needs.
        """
        ...

    def next(self) -> Point:
        """
        The destination now: the current one until it is reached or no longer
        allowed. `DESTINATION`'s update.
        """
        ...

    def abandon(self) -> Point:
        """Movement recovery's Abandon: a different destination."""
        ...


class DestinationProvider(Provider):
    """
    Serves `DESTINATION`, where the rotation heads, and `DESTINATION_PLATFORM`,
    the platform it is on, from the source the profile's rotation names.

    Configured from the profile: `rotation`, or `smart_rotation_enabled`, names
    the source (`rotation_name`), and `mob_count_threshold` is how many mobs the
    `smart` one steps towards. `setup()` draws the first destination on every
    platform: nothing is known yet of which a Path reaches.

    What the sources call on it, beside `read` and `refresh`, is under "what
    the sources ask of it".
    """

    #: Its own reads (what `wander_in_area` reads: the map, the position to
    #: judge arrival with, and the area's stretches), and every registered
    #: source's: `register_source` computes it from `SOURCES`.
    needs: ClassVar[tuple[Key[Any], ...]] = AreaWanderSource.needs

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        rotation: object = None,
        smart_rotation_enabled: object = None,
        hunting_area: object = None,
        mob_count_threshold: int | None = None,
        **settings: object,
    ) -> None:
        """
        :param rotation: The rotation's name, one of `ROTATIONS`.
        :param smart_rotation_enabled: Before `rotation`: true names `smart`.
        :param hunting_area: A saved area, with `rotation: hunting_area` only.
        :param mob_count_threshold: How many mobs the `smart` source steps
            towards. Required with it.
        """
        super().__init__(*args, **settings)
        self._rotation_settings = {
            "rotation": rotation,
            "smart_rotation_enabled": smart_rotation_enabled,
            "hunting_area": hunting_area,
        }
        self.mob_count_threshold = mob_count_threshold
        #: The source served, the `random` one `wander` serves, and the one
        #: `wander_in_area` serves. Built by `setup()`.
        self.source: DestinationSource
        self.wanderer: RandomSource
        self.area_wanderer: AreaWanderSource
        #: Whether the destination was drawn knowing which platforms a Path
        #: reaches; one that was not is checked once they are known.
        self._checked = True

    def setup(self) -> None:
        """
        :raises StartupRefused: The profile's rotation is refused, its source
            is not built yet or refuses the profile, or the Bot's map isn't
            known.
        """
        self.source = self._source()(self)
        self.wanderer = RandomSource(self)
        self.area_wanderer = AreaWanderSource(self)
        world_map = self.world_map()
        self.register(DESTINATION, self.source.next, initial_value=self.random_point())
        self.register(
            DESTINATION_PLATFORM,
            lambda: world_map.platform_at(self.read(DESTINATION)),
        )

    def _source(self) -> type[DestinationSource]:
        """
        The source the profile's rotation names.
        :raises StartupRefused: The rotation settings are refused
            (`rotation_name`), or name a rotation no source is registered for.
        """
        try:
            name = rotation_name(self._rotation_settings)
        except ProfileError as error:
            raise StartupRefused(f"{self}: {error}") from error
        source = SOURCES.get(name)
        if source is None:
            raise StartupRefused(
                f"{self}: `rotation: {name}` names a rotation whose destination "
                "source is not built yet."
            )
        return source

    # --- what others ask of it ---------------------------------------------------

    def abandon(self) -> Point | None:
        """
        Drop the destination the rotation is heading for and take a different
        one from the source: movement recovery's **Abandon** rung (`CONTEXT.md`
        -> Reaction Ladder). The sources keep the *current* destination until the
        character arrives, which is exactly what keeps a Stuck loop stuck, so the
        new one is set here.

        The new one may land back on the same platform. That is not worth
        guarding: the ladder is already at Abandon, so the next symptom
        escalates.
        :return: The new destination; None, with nothing changed, while
            `DESTINATION` is claimed: its holder decides where the character goes.
        """
        claim = self.claimed(DESTINATION)
        if claim is not None:
            logger.info("%s abandons nothing: %s.", self, claim)
            return None
        destination = self.source.abandon()
        self.store(DESTINATION, destination)
        self.refresh(DESTINATION_PLATFORM)
        return destination

    # --- what the sources ask of it ----------------------------------------------

    def checked_destination(self) -> Point:
        """
        The destination now, or a fresh draw when it was drawn before
        reachability was known, and the platform it is on turns out to be one no
        Path reaches from the character.
        """
        target = self.read(DESTINATION)
        if self._checked:
            return target
        among = self._reachable()
        if among is None:
            return target
        self._checked = True
        world_map = self.world_map()
        if world_map.platform_at(target) in among:
            return target
        logger.info("%s: destination %s is on no reachable platform.", self, target)
        redrawn = world_map.random_point(among)
        self.store_platform(redrawn)
        return redrawn

    def destination_platform(self) -> Platform | None:
        """The platform the destination is on, read now."""
        return self.refresh(DESTINATION_PLATFORM)

    def store_platform(self, destination: Point) -> None:
        """Set `DESTINATION_PLATFORM` to the platform `destination` is on."""
        self.store(DESTINATION_PLATFORM, self.world_map().platform_at(destination))

    def random_point(self) -> Point:
        """
        A random point on the platforms a Path reaches from the character, or
        on every platform before the graph and a position are known.
        """
        among = self._reachable()
        self._checked = among is not None
        return self.world_map().random_point(among)

    def position(self) -> Reading[VirtualPosition]:
        """The character's position, as `position_or_unsure` reads it."""
        return position_or_unsure(self)

    def world_map(self) -> WorldMap:
        """
        The bot's map.
        :raises StartupRefused: It isn't known (the profile names no map).
        """
        world_map = self.read(WORLD_MAP)
        if world_map is None:
            raise StartupRefused(
                "no map to rotate on: the bot's map isn't known (name it with the "
                "profile's `map` setting)"
            )
        return world_map

    def target_reached(self, position: Point, target: Point) -> None:
        """
        Record that a source judged the character to have arrived. Every place
        that judges arrival calls this, so the count means one thing. While a
        DecisionMaker claims `DESTINATION` with `wander`, its arrivals are
        recorded too, so a count of these against `movement.plan_started`
        (Rotation only) runs higher then.

        Takes the values the caller just judged arrival with, rather than
        reading them again: a read can refresh a thresholded key, and telemetry
        must not do work inside the thing it observes. Both are virtual px; the
        canvas fields are where the minimap draws the marker for each
        (`marker_of_feet`). It carries no Correlation ID: a Provider's records
        belong to no decision (ADR 0004).
        """
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            # No minimap, no position read: nothing is judged to arrive there.
            return
        transform = world_map.minimap
        self.emit(
            MOVEMENT_TARGET_REACHED,
            target_reached_payload(
                marker_of_feet(transform, position),
                marker_of_feet(transform, target),
                virtual_position=position,
                virtual_target=target,
            ),
        )

    # --- its own -----------------------------------------------------------------

    def _reachable(self) -> tuple[Platform, ...] | None:
        """
        The platforms a Path reaches from the character, or None while that
        isn't known, or no Path is planned on this Bot (`PathingProvider`).
        Not in `needs`: `PathingProvider` plans to `DESTINATION`, so this
        Provider is set up first and cannot need its keys back.
        """
        # Imported here: the pathing module imports this one, for DESTINATION.
        from .pathing import reachable_platforms

        return reachable_platforms(self.data)


#: Where the rotation heads next, in virtual px. Steerable: a DecisionMaker that
#: claims it decides where the character goes. Refreshed only when asked to.
DESTINATION: Key[Point] = Key("destination", DestinationProvider, steerable=True)
#: The platform `DESTINATION` is on, or None when it is on none.
DESTINATION_PLATFORM: Key[Platform | None] = Key(
    "destination_platform", DestinationProvider
)


#: What the Provider reads itself, whatever the source.
_OWN_NEEDS = DestinationProvider.needs
#: The destination sources, by the name the profile's `rotation` gives them.
#: Their names are `ROTATIONS`.
SOURCES: dict[str, type[DestinationSource]] = {}


def register_source(name: str, source: type[DestinationSource]) -> None:
    """
    Serve `source` when the profile's rotation is `name`. The Provider's `needs`
    becomes its own and every registered source's.
    """
    SOURCES[name] = source
    DestinationProvider.needs = tuple(
        dict.fromkeys(
            (*_OWN_NEEDS, *(key for each in SOURCES.values() for key in each.needs))
        )
    )


register_source("random", RandomSource)
register_source("smart", SmartSource)
register_source("hunting_area", HuntingAreaSource)


def wander(provider: Provider) -> Point:
    """
    A source for `DESTINATION` that wanders the map's platforms: the `random`
    source's destinations, a new random one each time the current one is
    reached, whatever rotation the profile names. `CheckMobsStillSpawn` claims
    it with this while it looks for mobs.
    """
    assert isinstance(provider, DestinationProvider), "DESTINATION's own Provider"
    return provider.wanderer.next()


def wander_in_area(provider: Provider) -> Point:
    """
    A source for `DESTINATION` that wanders the Hunting Area: random points on
    `AREA_STRETCHES`, a new one each time the current one is reached.
    `CheckMobsStillSpawn` claims it with this, instead of `wander`, when there
    is an area.
    """
    assert isinstance(provider, DestinationProvider), "DESTINATION's own Provider"
    return provider.area_wanderer.next()
