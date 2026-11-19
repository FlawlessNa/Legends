"""
The `hunting_area` destination source: every destination inside the Hunting
Area (#571, spec section 7). Where a cast reaches the most mobs, else the part of
the area seen least recently, and away from players who have settled.

**The mobs it counts** are the ones found on the current frame, placed in
virtual px through that frame's Camera, that stand inside the rectangle
(`HUNTING_AREA`). Once someone has settled (`AREA_PRESENCE`), a mob within
`NEAR` of one of `others` is not counted.

**What it picks**, each time it has to: for each stretch of `AREA_STRETCHES`,
the spots on it nearest each counted mob; the one whose cast reaches the most
mobs (`CAST_REACH`) wins, the nearest to the character on a tie, when it
reaches at least `min_mobs`. Otherwise it looks around: the middle of the cell
seen least recently, the nearest on a tie. A cell is seen when its middle is
inside the play area, in virtual px, on a refresh where the Camera is read.

**When it picks.** It keeps its destination until the character is within
`ARRIVAL` of it, then looks and picks again; a spot that still reaches
`min_mobs` is kept, and the character stands there, looking at most every
`LOOK_EVERY`. A destination no longer allowed (off `AREA_STRETCHES`, or within
`NEAR` of a settled player) is replaced at once.

**Crowded out.** Once someone has settled and no cell is free of them
(`free_share` 0), the destination is the character's last sure position, the one
destination that need not be on a stretch.

It decides where to go, never how: Paths are planned to it as to any
destination, on the whole map. Nothing here pauses, delays or cancels a cast.

`AreaWanderSource` is the mob-spawn failsafe's wandering inside the area:
random points on `AREA_STRETCHES`.
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal

from botting import PARENT_LOG
from botting.core import HANDLE, Key, StartupRefused
from maple.decision_makers.mob_detection import (
    get_mobs_positions_in_img,
    mobs_in_virtual_px,
)
from maple.decision_makers.providers.cast_reach import CAST_REACH
from maple.decision_makers.providers.client import FRAME
from maple.decision_makers.providers.hunting_area import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    HUNTING_AREA,
    NOBODY,
    AreaPresence,
    free_cells,
    near,
)
from maple.decision_makers.providers.map import POSITION_FUSION, WORLD_MAP
from maple.decision_makers.providers.minimap import POSITION
from maple.decision_makers.providers.mobs import MOBS
from maple.model.world.hunting_area import (
    HuntingArea,
    Stretch,
    cells,
    on_stretches,
    random_point,
)
from maple.telemetry_events import (
    ROTATION_DESTINATION_PICKED,
    DestinationPickedPayload,
)

if TYPE_CHECKING:
    from maple.decision_makers.providers.destination import DestinationProvider
    from maple.model.navigation import Point
    from maple.screen.position import Camera

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: Why a destination was picked, as `rotation.destination_picked` says.
type Why = Literal["mobs", "look_around", "abandon", "crowded_out"]

#: How far a cast reaches from the feet, in virtual px: left, right, up, down.
type Reach = tuple[float, float, float, float]

#: How many random points `abandon` tries before it takes a free cell's middle.
_TRIES: Final = 32


@dataclass(frozen=True, slots=True)
class Look:
    """
    What one look at the frame found.

    :ivar mobs: The mobs counted, in virtual px: inside the rectangle, and not
        within `NEAR` of a settled player.
    :ivar reach: How far a cast reaches, in virtual px through that frame's
        Camera; None when the Camera was not read, and then no mob is counted.
    """

    mobs: tuple[Point, ...] = ()
    reach: Reach | None = None


#: A look on a frame whose Camera was not read.
BLIND: Final = Look()


def reaches(spot: Point, mobs: Sequence[Point], reach: Reach) -> int:
    """How many of `mobs` a cast from `spot`, the character's feet, reaches."""
    x, y = spot
    left, right, up, down = reach
    return sum(
        1 for mx, my in mobs if x - left <= mx <= x + right and y - up <= my <= y + down
    )


def best_spot(
    stretches: Sequence[Stretch],
    mobs: Sequence[Point],
    reach: Reach,
    here: Point | None,
    others: Sequence[Point] = (),
) -> tuple[Point, int] | None:
    """
    Of the spots on each stretch nearest each mob, outside `NEAR` of `others`,
    the one whose cast reaches the most mobs, the nearest to `here` on a tie;
    None with no mob.

    :returns: The spot and how many mobs it reaches.
    """
    best: tuple[Point, int] | None = None
    best_distance = math.inf
    for stretch in stretches:
        for mx, _ in mobs:
            x = min(max(mx, stretch.left), stretch.right)
            y = stretch.y_at(x)
            assert y is not None  # x is within the stretch
            spot = (x, y)
            if near(spot, others):
                continue
            count = reaches(spot, mobs, reach)
            distance = 0.0 if here is None else math.dist(spot, here)
            if best is None or (count, -distance) > (best[1], -best_distance):
                best, best_distance = (spot, count), distance
    return best


class HuntingAreaSource:
    """
    Destinations inside the Hunting Area: towards the mobs, else around the
    area, and away from settled players. See the module's docstring.

    Refuses a profile with no `mob_count_threshold`, as `smart` does: with no
    `min_mobs`, no spot is worth going to.
    """

    #: What it reads through the Provider: the window, the frame and the mobs to
    #: find on it, the map, the position with the Camera it was read through,
    #: the area and where in it the character may go, who has settled, and
    #: what a cast reaches.
    needs: ClassVar[tuple[Key[Any], ...]] = (
        HANDLE,
        FRAME,
        MOBS,
        WORLD_MAP,
        POSITION_FUSION,
        POSITION,
        HUNTING_AREA,
        AREA_STRETCHES,
        AREA_PRESENCE,
        CAST_REACH,
    )

    #: Arrival, in virtual px: smart rotation's, 4 minimap px.
    ARRIVAL = 64.0
    #: Seconds between two looks for mobs while the character stands at its
    #: destination: smart rotation's time on target.
    LOOK_EVERY = 0.75

    def __init__(self, provider: DestinationProvider) -> None:
        """
        :raises StartupRefused: The profile has no `mob_count_threshold`.
        """
        if provider.mob_count_threshold is None:
            raise StartupRefused(
                f"{provider} hunts a Hunting Area, and the profile has no "
                "mob_count_threshold: set one, or rotate another way."
            )
        self.provider = provider
        self.rng = random.Random()
        #: Where it heads, and whether arrival there was recorded.
        self._destination: Point | None = None
        self._arrived = False
        #: When it last looked for mobs.
        self._looked_at = -math.inf
        #: Whether it is crowded out.
        self._crowded = False
        #: The character's last sure position.
        self._last_sure: Point | None = None
        #: When each cell was last seen, by its middle.
        self._seen: dict[Point, float] = {}

    # --- DestinationSource -------------------------------------------------------

    def next(self) -> Point:
        """
        The current destination until the character arrives within `ARRIVAL`,
        or it stops being allowed; then the next pick. See the module's
        docstring.
        """
        now = self.provider.data.clock()
        here = self._here()
        self._mark_seen(self._camera(), now)
        presence = self._presence()
        stretches = self._stretches()
        others = presence.others if presence.settled else ()
        if self._crowded_out(presence, stretches, others):
            return self._crowd_out()
        if self._crowded:
            # Room again: pick at once.
            self._crowded = False
            return self._pick(here, now, stretches, others)
        destination = self._destination
        if destination is None or not self._allowed(destination, stretches, others):
            return self._pick(here, now, stretches, others)
        if here is None or math.dist(here, destination) > self.ARRIVAL:
            return destination
        if not self._arrived:
            self._arrived = True
            self.provider.target_reached(here, destination)
        elif now - self._looked_at < self.LOOK_EVERY:
            return destination
        look = self._look(now, others)
        if look.reach is not None and (
            reaches(destination, look.mobs, look.reach) >= self._min_mobs()
        ):
            return destination
        return self._pick(here, now, stretches, others, look)

    def abandon(self) -> Point:
        """
        Movement recovery's Abandon: a random point on `AREA_STRETCHES`, outside
        `NEAR` of a settled player; the character's last sure position while
        crowded out.
        """
        presence = self._presence()
        stretches = self._stretches()
        others = presence.others if presence.settled else ()
        if self._crowded_out(presence, stretches, others):
            return self._crowd_out()
        free = free_cells(stretches, others)
        destination = next(
            (
                point
                for point in (random_point(free, self.rng) for _ in range(_TRIES))
                if not near(point, others)
            ),
            None,
        )
        if destination is None:
            destination = self.rng.choice(free).middle
        return self._head_for(destination, "abandon", 0)

    # --- its reads ---------------------------------------------------------------

    def _here(self) -> Point | None:
        """The character's position, None when unsure; the last sure one kept."""
        reading = self.provider.position()
        if reading.value is None:
            return None
        self._last_sure = (reading.value.x, reading.value.y)
        return self._last_sure

    def _camera(self) -> Camera | None:
        """The Camera the last position read matched; None when it matched none."""
        fusion = self.provider.read(POSITION_FUSION)
        return None if fusion is None else fusion.camera

    def _presence(self) -> AreaPresence:
        return self.provider.read(AREA_PRESENCE) or NOBODY

    def _stretches(self) -> tuple[Stretch, ...]:
        stretches = self.provider.read(AREA_STRETCHES)
        assert stretches, "with `rotation: hunting_area`, the area holds a stretch"
        return stretches

    def _served(self) -> Point:
        """The destination the Provider serves now."""
        # Imported here: the destination module imports this one.
        from maple.decision_makers.providers.destination import DESTINATION

        return self.provider.read(DESTINATION)

    def _area(self) -> HuntingArea:
        area = self.provider.read(HUNTING_AREA)
        assert area is not None, "with `rotation: hunting_area`, there is an area"
        return area

    def _min_mobs(self) -> int:
        reach = self.provider.read(CAST_REACH)
        assert self.provider.mob_count_threshold is not None  # refused otherwise
        return self.provider.mob_count_threshold if reach is None else reach.min_mobs

    # --- looking -----------------------------------------------------------------

    def _look(self, now: float, others: Sequence[Point]) -> Look:
        """
        Find the mobs on a fresh frame, placed through the Camera its position
        read matched, and mark the cells it shows seen. `BLIND` when the Camera
        is not read, or no cast reach is known.
        """
        provider = self.provider
        self._looked_at = now
        frame = provider.refresh(FRAME)
        # Read on this frame, so its Camera is the one that places the mobs.
        provider.refresh(POSITION)
        camera = self._camera()
        reach = provider.read(CAST_REACH)
        if camera is None or not frame.ok:
            return BLIND
        self._mark_seen(camera, now)
        if reach is None:
            return BLIND
        found = get_mobs_positions_in_img(
            frame.pixels, provider.read(MOBS), provider.read(HANDLE)
        )
        area = self._area()
        mobs = tuple(
            mob
            for mob in mobs_in_virtual_px(found, frame.client_size, camera)
            if area.contains(mob) and not near(mob, others)
        )
        return Look(mobs, reach.in_virtual(frame.client_size, camera.play_area))

    def _mark_seen(self, camera: Camera | None, now: float) -> None:
        """Every cell whose middle is inside the Camera's play area is seen now."""
        if camera is None:
            return
        left, top = camera.x, camera.y
        right, bottom = left + camera.play_area[0], top + camera.play_area[1]
        for cell in cells(self._stretches()):
            x, y = cell.middle
            if left <= x <= right and top <= y <= bottom:
                self._seen[cell.middle] = now

    # --- picking -----------------------------------------------------------------

    def _pick(
        self,
        here: Point | None,
        now: float,
        stretches: Sequence[Stretch],
        others: Sequence[Point],
        look: Look | None = None,
    ) -> Point:
        """Look, unless just done, then head for the best spot or look around."""
        if look is None:
            look = self._look(now, others)
        if look.reach is not None:
            best = best_spot(stretches, look.mobs, look.reach, here, others)
            if best is not None and best[1] >= self._min_mobs():
                return self._head_for(best[0], "mobs", best[1])
        middle = self._least_seen(here, stretches, others)
        count = 0 if look.reach is None else reaches(middle, look.mobs, look.reach)
        return self._head_for(middle, "look_around", count)

    def _least_seen(
        self, here: Point | None, stretches: Sequence[Stretch], others: Sequence[Point]
    ) -> Point:
        """The middle of the free cell seen least recently, the nearest on a tie."""
        start = here or self._last_sure
        free = free_cells(stretches, others)
        assert free, "a pick is made only while a cell is free"
        cell = min(
            free,
            key=lambda c: (
                self._seen.get(c.middle, -math.inf),
                0.0 if start is None else math.dist(c.middle, start),
            ),
        )
        return cell.middle

    def _allowed(
        self, destination: Point, stretches: Sequence[Stretch], others: Sequence[Point]
    ) -> bool:
        """On a stretch of `AREA_STRETCHES`, outside `NEAR` of a settled player."""
        return on_stretches(destination, stretches) and not near(destination, others)

    def _crowded_out(
        self,
        presence: AreaPresence,
        stretches: Sequence[Stretch],
        others: Sequence[Point],
    ) -> bool:
        """Someone has settled, and no cell is free of them."""
        return presence.settled and (
            presence.free_share == 0.0 or not free_cells(stretches, others)
        )

    def _crowd_out(self) -> Point:
        """
        Stay where the character last surely was, announced once on becoming
        crowded out. Before any sure read, the destination it has.
        """
        if not self._crowded:
            self._crowded = True
            stay = self._last_sure or self._destination or self._served()
            self._head_for(stay, "crowded_out", 0, announce=True)
        assert self._destination is not None
        return self._destination

    def _head_for(
        self, destination: Point, why: Why, mobs: int, *, announce: bool = False
    ) -> Point:
        """
        Make `destination` the one it heads for, and say so when it is a new one
        (`announce`: whether it is or not).
        """
        if destination != self._destination or announce:
            payload: DestinationPickedPayload = {
                "x": float(destination[0]),
                "y": float(destination[1]),
                "why": why,
                "mobs": int(mobs),
            }
            self.provider.emit(ROTATION_DESTINATION_PICKED, payload)
            logger.debug(
                "%s heads for %s: %s, %s mob(s).", self, destination, why, mobs
            )
        if destination != self._destination:
            self._destination = destination
            self._arrived = False
            self.provider.store_platform(destination)
        return destination


class AreaWanderSource:
    """
    The mob-spawn failsafe's wandering inside the Hunting Area: a random point
    on `AREA_STRETCHES`, drawn again once the character is within `ARRIVAL` of
    it, or once it is no longer on one. What `wander_in_area` claims
    `DESTINATION` with.
    """

    #: What it reads through the Provider: the position, and the stretches.
    needs: ClassVar[tuple[Key[Any], ...]] = (WORLD_MAP, POSITION, AREA_STRETCHES)

    #: Arrival, in virtual px: the `random` source's.
    ARRIVAL = 160.0

    def __init__(self, provider: DestinationProvider) -> None:
        self.provider = provider
        self.rng = random.Random()
        self._destination: Point | None = None

    def next(self) -> Point:
        """
        The current point until the character is within `ARRIVAL` of it, or it
        is off `AREA_STRETCHES`; then a new one. An unsure position holds it.
        """
        stretches = self._stretches()
        target = self._destination
        if target is None or not on_stretches(target, stretches):
            return self._draw(stretches)
        reading = self.provider.position()
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.ARRIVAL:
            return target
        self.provider.target_reached(position, target)
        return self._draw(stretches)

    def abandon(self) -> Point:
        """A fresh random point on `AREA_STRETCHES`."""
        return self._draw(self._stretches())

    def _stretches(self) -> tuple[Stretch, ...]:
        stretches = self.provider.read(AREA_STRETCHES)
        assert stretches, "wandering in the area needs a Hunting Area"
        return stretches

    def _draw(self, stretches: Sequence[Stretch]) -> Point:
        self._destination = random_point(stretches, self.rng)
        self.provider.store_platform(self._destination)
        return self._destination
