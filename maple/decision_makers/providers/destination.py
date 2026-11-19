"""
The rotation's destination: where the character heads next, in virtual px on
the Bot's `WorldMap`, and the platform it is on (#398).

`DestinationProvider` holds the rotation's two modes, chosen by the profile,
and movement recovery's Abandon (#441). `DESTINATION` is the first
steerable Data Key: a DecisionMaker that must send the character somewhere else
claims it (`CheckMobsStillSpawn` wanders, `TrialRunner` walks its schedule), and
the Provider's own value comes back when the Claim is released.

**The modes.** A map from `game_data` has no feature cycle, so the destination
is a random point on the map's platforms (`WorldMap.random_point`, platforms
weighted by their width), redrawn once the character is within
`BASE_ROTATION_THRESHOLD` of it. With `smart_rotation_enabled`, it is redrawn
once the character has stood within `SMART_ROTATION_THRESHOLD` of it for
`TIME_ON_TARGET`: towards the side most mobs are on, when enough are around,
else anywhere on its platform. Custom rotation patterns are a later epic.

**Only platforms a Path reaches.** The draw is restricted to the platforms the
foothold graph reaches from the character's position, when the graph and a
position are known (`PathingProvider.reachable_platforms`): some maps have
platforms nothing reaches (on Damp Forest, 7 of its 11, 37 % of their width,
from its widest platform), and a destination there is one no Path joins, which
only movement recovery would ever drop. One drawn before then is checked, and
drawn again, once they are known.
"""

import logging
import math
import statistics
import time
from collections.abc import Sequence
from typing import Any

import numpy as np

from botting import PARENT_LOG
from botting.core import HANDLE, Key, Provider, StartupRefused
from botting.screen import Frame, Reading
from maple.decision_makers.mob_detection import (
    get_mobs_positions_in_img,
    mobs_in_virtual_px,
)
from maple.model.navigation import Point
from maple.model.world import Platform, WorldMap
from maple.screen.position import VirtualPosition, marker_of_feet
from maple.telemetry_events import MOVEMENT_TARGET_REACHED, target_reached_payload

from .client import FRAME
from .map import POSITION_FUSION, WORLD_MAP
from .minimap import POSITION, position_or_unsure
from .mobs import MOBS
from .on_screen import ON_SCREEN_POSITION

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class DestinationProvider(Provider):
    """
    Serves `DESTINATION`, where the rotation heads, and `DESTINATION_PLATFORM`,
    the platform it is on.

    Configured from the profile: `smart_rotation_enabled` picks the mode, and
    `mob_count_threshold` is how many mobs smart rotation steps towards.
    `setup()` draws the first destination on every platform: nothing is known
    yet of which a Path reaches.
    """

    needs = (HANDLE, FRAME, MOBS, WORLD_MAP, POSITION_FUSION, POSITION)

    #: Arrival for the basic rotation, in virtual px: 10 minimap px, as it was
    #: judged in minimap px before #398 (16 virtual px each, `mag` 4).
    BASE_ROTATION_THRESHOLD = 160.0
    #: Arrival for smart rotation: 4 minimap px.
    SMART_ROTATION_THRESHOLD = 64.0
    #: How far smart rotation steps towards the mobs at most: 10 minimap px.
    SMART_ROTATION_STEP = 160.0
    #: Seconds smart rotation stands on its destination before it draws the next.
    TIME_ON_TARGET = 0.75
    #: The fewest mobs smart rotation steps towards, whatever the profile says.
    MIN_MOBS_THRESHOLD = 2

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        smart_rotation_enabled: bool = False,
        mob_count_threshold: int | None = None,
        **settings: object,
    ) -> None:
        """
        :param smart_rotation_enabled: Draw the next destination the smart way.
        :param mob_count_threshold: How many mobs smart rotation steps towards.
            Required with it.
        """
        super().__init__(*args, **settings)
        self.smart_rotation = smart_rotation_enabled
        self.mob_count_threshold = mob_count_threshold
        #: Whether the destination was drawn knowing which platforms a Path
        #: reaches; one that was not is checked once they are known.
        self._checked = True
        #: Smart rotation: whether the character has yet to be judged on its
        #: destination, and when it was.
        self._first_time_on_target = True
        self._last_target_reached_at = 0.0

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot's map isn't known, or smart rotation is
            on with no `mob_count_threshold`.
        """
        if self.smart_rotation and self.mob_count_threshold is None:
            raise StartupRefused(
                f"{self} rotates the smart way, and the profile has no "
                "mob_count_threshold: set one, or turn smart_rotation_enabled off."
            )
        world_map = self._world_map()
        self.register(
            DESTINATION,
            self._smart if self.smart_rotation else self.random_destination,
            initial_value=self._random_point(),
        )
        self.register(
            DESTINATION_PLATFORM,
            lambda: world_map.platform_at(self.read(DESTINATION)),
        )

    # --- what others ask of it ---------------------------------------------------

    def abandon(self) -> Point | None:
        """
        Drop the destination the rotation is heading for and pick a different
        one: movement recovery's **Abandon** rung (`CONTEXT.md` -> Reaction
        Ladder). The modes keep the *current* destination until the character
        arrives, which is exactly what keeps a Stuck loop stuck, so the new one
        is set here: a fresh random point on a reachable platform.

        The draw may land back on the same platform. That is not worth guarding:
        the ladder is already at Abandon, so the next symptom escalates.
        :return: The new destination; None, with nothing changed, while
            `DESTINATION` is claimed: its holder decides where the character goes.
        """
        claim = self.claimed(DESTINATION)
        if claim is not None:
            logger.info("%s abandons nothing: %s.", self, claim)
            return None
        destination = self._random_point()
        self.store(DESTINATION, destination)
        self.refresh(DESTINATION_PLATFORM)
        return destination

    def random_destination(self) -> Point:
        """
        The basic mode: the current destination until the character is within
        `BASE_ROTATION_THRESHOLD` of it, then a new random one. An unsure
        position holds the destination: arrival can't be judged from it.

        Also what `wander` claims `DESTINATION` with, whatever the profile's mode.
        """
        target = self._checked_target(self.read(DESTINATION))
        reading = self._position()
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.BASE_ROTATION_THRESHOLD:
            return target
        self._emit_target_reached(position, target)
        destination = self._random_point()
        self.store(DESTINATION_PLATFORM, self._world_map().platform_at(destination))
        return destination

    # --- the smart mode ----------------------------------------------------------

    def _smart(self) -> Point:
        """
        Determines the next destination "the smart way". Uses the character's
        on-screen location to get a wide view of its platform. If there are
        mobs, the destination is the "average" position of those on the side
        where there are most, on the destination's platform. Otherwise, a random
        point on that platform.
        """
        target = self._checked_target(self.read(DESTINATION))
        reading = self._position()
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.SMART_ROTATION_THRESHOLD:
            self._first_time_on_target = True
            return target

        # On target: has it been for longer than TIME_ON_TARGET?
        if self._first_time_on_target:
            self._emit_target_reached(position, target)
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return target
        elif time.perf_counter() - self._last_target_reached_at < self.TIME_ON_TARGET:
            return target

        # Reached once it has stood on target for longer than TIME_ON_TARGET.
        self._first_time_on_target = True
        # Check for mobs in the vicinity.
        self.refresh(FRAME)
        on_screen_pos = self._on_screen_position()
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            frame = self.read(FRAME)
            shape = frame.pixels.shape
            mask = np.zeros(shape, np.uint8)
            mask[
                max(0, y1 - 100) : min(shape[0], y2 + 100),
                max(0, x1 - 500) : min(shape[1], x2 + 500),
            ] = 255
            mobs_locations = get_mobs_positions_in_img(
                frame.pixels, self.read(MOBS), self.read(HANDLE), mask=mask
            )
            assert self.mob_count_threshold is not None, "setup() refuses none"
            if len(mobs_locations) >= max(
                self.mob_count_threshold, self.MIN_MOBS_THRESHOLD
            ):
                stepped = self._step_towards_mobs(mobs_locations, frame, target)
                if stepped is not None:
                    return stepped

        platform = self.refresh(DESTINATION_PLATFORM)
        if platform is None:
            return self._random_point()
        return self._world_map().random_point((platform,))

    def _on_screen_position(self) -> tuple[int, int, int, int] | None:
        """
        Where the character was last found on screen, refreshed when stale, as
        `MobsHitting`, which reads `ON_SCREEN_POSITION`, has it. Not in `needs`:
        only this mode looks at it, and a Bot that builds this Provider without
        hitting mobs (a calibration sitting) has no chat reader to find the
        character with. None when nothing reads it.
        """
        if not self.data.is_provided(ON_SCREEN_POSITION):
            return None
        last_known = self.data.peek(ON_SCREEN_POSITION)
        return self.data.read(ON_SCREEN_POSITION) or last_known

    def _step_towards_mobs(
        self, mobs: list[Sequence[int]], frame: Frame, target: Point
    ) -> Point | None:
        """
        A point on the destination's platform, towards the side most of `mobs`
        are on: their mean distance from the character, at most
        `SMART_ROTATION_STEP`. The mobs are placed in virtual px through the
        camera of the frame they were found on; None when that frame's camera
        or position isn't read, or the destination is on no platform.
        """
        # Read on this frame, so its camera is the one that places the mobs.
        reading = self.refresh(POSITION)
        fusion = self.read(POSITION_FUSION)
        camera = None if fusion is None else fusion.camera
        platform = self._world_map().platform_at(target)
        if camera is None or reading.value is None or platform is None:
            return None
        here = reading.value.x
        xs = [x for x, _ in mobs_in_virtual_px(mobs, frame.client_size, camera)]
        left = [here - x for x in xs if x < here]
        right = [x - here for x in xs if x >= here]
        if len(left) > len(right):
            x = max(
                here - min(statistics.mean(left), self.SMART_ROTATION_STEP),
                platform.left,
            )
        else:
            x = min(
                here + min(statistics.mean(right), self.SMART_ROTATION_STEP),
                platform.right,
            )
        y = platform.y_at(x)
        return None if y is None else (x, y)

    # --- shared by the modes -----------------------------------------------------

    def _random_point(self) -> Point:
        """
        A random point on the platforms a Path reaches from the character, or
        on every platform before the graph and a position are known.
        """
        among = self._reachable()
        self._checked = among is not None
        return self._world_map().random_point(among)

    def _checked_target(self, target: Point) -> Point:
        """
        `target`, or a fresh draw when it was drawn before reachability was
        known, and the platform it is on turns out to be one no Path reaches
        from the character.
        """
        if self._checked:
            return target
        among = self._reachable()
        if among is None:
            return target
        self._checked = True
        world_map = self._world_map()
        if world_map.platform_at(target) in among:
            return target
        logger.info("%s: destination %s is on no reachable platform.", self, target)
        redrawn = world_map.random_point(among)
        self.store(DESTINATION_PLATFORM, world_map.platform_at(redrawn))
        return redrawn

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

    def _position(self) -> Reading[VirtualPosition]:
        """The character's position, as `position_or_unsure` reads it."""
        return position_or_unsure(self)

    def _emit_target_reached(self, position: Point, target: Point) -> None:
        """
        Record that a mode judged the character to have arrived. Every place
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

    def _world_map(self) -> WorldMap:
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


#: Where the rotation heads next, in virtual px. Steerable: a DecisionMaker that
#: claims it decides where the character goes. Refreshed only when asked to.
DESTINATION: Key[Point] = Key("destination", DestinationProvider, steerable=True)
#: The platform `DESTINATION` is on, or None when it is on none.
DESTINATION_PLATFORM: Key[Platform | None] = Key(
    "destination_platform", DestinationProvider
)


def wander(provider: Provider) -> Point:
    """
    A source for `DESTINATION` that wanders the map's platforms: a new random
    destination each time the current one is reached (`random_destination`),
    whatever mode the profile picks. `CheckMobsStillSpawn` claims it with this
    while it looks for mobs.
    """
    assert isinstance(provider, DestinationProvider), "DESTINATION's own Provider"
    return provider.random_destination()
