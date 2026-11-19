"""
The Hunting Area the rotation hunts, where in it the character may go, and
whether another player has settled in it (#571, spec section 5).

`HuntingAreaProvider` serves three keys, each `None` when the profile's rotation
is not `hunting_area`:

- `HUNTING_AREA`, resolved once in `setup()`: the saved area the profile's
  `hunting_area` names, or, with none named, the one the maintainer chooses in
  the launch window (`maple/launchers/hunting_area_window.py`). Emits
  `rotation.area_set` once.
- `AREA_STRETCHES`, the one definition of where the character may go: the
  area's stretches on the Platforms a Path reaches from the character. Every
  stretch of the area until the foothold graph and a position are known; every
  stretch, with one error logged, when none of them is reachable, and Movement
  recovery handles it as it does today.
- `AREA_PRESENCE`, whether someone has **Settled** (`CONTEXT.md`), who is near,
  and how much of the area is left to go for. The logic is `PresenceCounter`, a
  plain class on an injected clock.

**Another rotation pays nothing.** The Destination Provider's `needs` is every
source's, so this Provider is built for every bot with a destination. With
another rotation it does no I/O and refuses nothing, and every key is
registered with its value, so building it reads nothing.

The tuning constants below are where Settled is decided. They are starting
values, tuned from what live Sessions show: changing one is a code edit and a
restart.
"""

import logging
import math
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final

from botting import PARENT_LOG
from botting.core import HANDLE, Key, Provider, StartupRefused
from botting.screen import Reading
from maple.decision_makers.rotation_setting import rotation_name
from maple.launchers import hunting_area_window
from maple.launchers.profile import ProfileError
from maple.model.world import HuntingArea, WorldMap
from maple.model.world.hunting_area import (
    HUNTING_AREAS,
    EmptyHuntingArea,
    Stretch,
    UnknownHuntingArea,
    cells,
    load_area,
)
from maple.telemetry_events import ROTATION_AREA_SET, AreaSetPayload

from .client import FRAME
from .map import WORLD_MAP
from .other_players import ANOTHER, OTHER_PLAYERS, OtherPlayers
from .screen_readers import MINIMAP_READER

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

type Point = tuple[float, float]

NEAR: Final = 350.0
"""Virtual px: another player this close to a spot keeps the character from it
once someone has settled, and one this close to the rectangle is in `others`."""

SETTLE_WINDOW: Final = 60.0
"""Seconds: how far back the "inside" samples are added up."""

SETTLE_PRESENCE: Final = 30.0
"""Seconds: the "inside" samples of the last `SETTLE_WINDOW` that start Settled."""

LEAVE_AFTER: Final = 60.0
"""Seconds with no "inside" sample after which Settled ends."""

SAMPLE_CAP: Final = 2.0
"""Seconds: the most a sample stands for, however long since the one before."""

OTHERS_MEMORY: Final = 5.0
"""Seconds: how long a player seen near the area stays in `others`, so that one
read missing their marker does not drop them."""

#: The rotation this Provider serves.
HUNTING_AREA_ROTATION: Final = "hunting_area"


@dataclass(frozen=True, slots=True)
class AreaPresence:
    """
    Who is in or near the Hunting Area, as the minimap's markers say.

    :ivar settled: Whether another player has settled in the area.
    :ivar others: Every other player seen in the sure reads of the last
        `OTHERS_MEMORY` seconds inside the rectangle or within `NEAR` of it, in
        virtual px. A marker has no identity, so one player seen on several
        reads is several points.
    :ivar free_share: The share of the cells of `AREA_STRETCHES` whose middle
        is farther than `NEAR` from every one of `others`; 1 when no one has
        settled.
    :ivar inside: How many other players were inside the rectangle on the last
        sure read.
    """

    settled: bool
    others: tuple[Point, ...]
    free_share: float
    inside: int


#: Before any sure read: no one there, nothing held back.
NOBODY: Final = AreaPresence(settled=False, others=(), free_share=1.0, inside=0)


class PresenceCounter:
    """
    Decides Settled from the sure reads of `OTHER_PLAYERS`, one sample each: is
    at least one other player inside the rectangle?

    A sample stands for the time since the sure sample before it, at most
    `SAMPLE_CAP`; the first stands for none. Settled starts when the "inside"
    samples of the last `SETTLE_WINDOW` stand for `SETTLE_PRESENCE` seconds or
    more, and ends once no sample has said "inside" for `LEAVE_AFTER`. An
    `UNSURE` read is no sample: it changes nothing.

    Counted per area, not per player: two players who each pass for 20 s, one
    after the other, read as one who stayed. That errs toward an alert.
    """

    def __init__(self, area: HuntingArea, clock: Callable[[], float]) -> None:
        """
        :param clock: Seconds, monotonic: when each sample is taken.
        """
        self.area = area
        self.clock = clock
        self._value = NOBODY
        self._settled = False
        #: When the last sure sample was taken.
        self._last_sample: float | None = None
        #: When the last "inside" sample was taken.
        self._last_inside: float | None = None
        #: The "inside" samples of the last `SETTLE_WINDOW`: (when, seconds).
        self._inside: deque[tuple[float, float]] = deque()
        #: The sure reads of the last `OTHERS_MEMORY`: (when, players near).
        self._seen: deque[tuple[float, tuple[Point, ...]]] = deque()

    @property
    def value(self) -> AreaPresence:
        """The presence after the last sample."""
        return self._value

    def sample(
        self, reading: Reading[OtherPlayers], stretches: Sequence[Stretch]
    ) -> AreaPresence:
        """
        Take one read of the other players into account.

        :param stretches: `AREA_STRETCHES`, whose cells `free_share` counts.
        :returns: The presence now; the last one, unchanged, on an `UNSURE` read.
        """
        players = reading.value
        if players is None:
            return self._value
        now = self.clock()
        seconds = (
            0.0
            if self._last_sample is None
            else min(now - self._last_sample, SAMPLE_CAP)
        )
        self._last_sample = now
        inside = [p for p in players.positions if self._distance(p) == 0.0]
        if inside:
            self._inside.append((now, seconds))
            self._last_inside = now
        while self._inside and now - self._inside[0][0] >= SETTLE_WINDOW:
            self._inside.popleft()
        self._seen.append(
            (now, tuple(p for p in players.positions if self._distance(p) <= NEAR))
        )
        while now - self._seen[0][0] >= OTHERS_MEMORY:
            self._seen.popleft()
        self._settle(now)
        others = tuple(dict.fromkeys(p for _, near in self._seen for p in near))
        self._value = AreaPresence(
            settled=self._settled,
            others=others,
            free_share=free_share(stretches, others) if self._settled else 1.0,
            inside=len(inside),
        )
        return self._value

    def _settle(self, now: float) -> None:
        if self._settled:
            assert self._last_inside is not None
            if now - self._last_inside >= LEAVE_AFTER:
                self._settled = False
        elif sum(seconds for _, seconds in self._inside) >= SETTLE_PRESENCE:
            self._settled = True

    def _distance(self, point: Point) -> float:
        """How far `point` is from the rectangle, in virtual px; 0 inside it."""
        area = self.area
        dx = max(area.left - point[0], 0.0, point[0] - area.right)
        dy = max(area.top - point[1], 0.0, point[1] - area.bottom)
        return math.hypot(dx, dy)


def free_share(stretches: Sequence[Stretch], others: Sequence[Point]) -> float:
    """
    The share of the stretches' cells whose middle is farther than `NEAR` from
    every one of `others`; 0 when there is no cell.
    """
    found = cells(stretches)
    if not found:
        return 0.0
    free = sum(
        1 for cell in found if all(math.dist(cell.middle, o) > NEAR for o in others)
    )
    return free / len(found)


class HuntingAreaProvider(Provider):
    """
    Serves `HUNTING_AREA`, `AREA_STRETCHES` and `AREA_PRESENCE`.

    Configured from the profile: `rotation` (or `smart_rotation_enabled`) names
    the rotation (`rotation_name`), and `hunting_area` the saved area to hunt.
    """

    needs = (WORLD_MAP, HANDLE, FRAME, MINIMAP_READER, OTHER_PLAYERS)

    #: Where the saved areas are, one file per map.
    FOLDER: ClassVar[Path] = HUNTING_AREAS
    #: Seconds `AREA_STRETCHES` and `AREA_PRESENCE` are served before a read
    #: refreshes them.
    REFRESH = 1.0

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        rotation: object = None,
        smart_rotation_enabled: object = None,
        hunting_area: object = None,
        **settings: object,
    ) -> None:
        """
        :param rotation: The rotation's name, one of `ROTATIONS`.
        :param smart_rotation_enabled: Before `rotation`: true names `smart`.
        :param hunting_area: The saved area to hunt, with `rotation:
            hunting_area` only; the launch window asks for one when not given.
        """
        super().__init__(*args, **settings)
        self._rotation_settings = {
            "rotation": rotation,
            "smart_rotation_enabled": smart_rotation_enabled,
            "hunting_area": hunting_area,
        }
        self._saved_name = None if hunting_area is None else str(hunting_area)
        #: Every stretch of the area. Set by `setup()` when there is an area.
        self._stretches: tuple[Stretch, ...] = ()
        self._presence: PresenceCounter | None = None
        #: The last `OTHER_PLAYERS` reading sampled: a read served from its
        #: cache is not a new sample.
        self._sampled: Reading[OtherPlayers] | None = None
        #: Whether "no stretch is reachable" was logged since one last was.
        self._unreachable_logged = False

    def setup(self) -> None:
        """
        :raises StartupRefused: With `rotation: hunting_area` only: the saved
            area is unknown or holds no Platform, the launch window cannot open
            or is closed without an area, or the Bot's map is not known. Each
            names the `hunting_area` setting. With another rotation, nothing.
        """
        if self._rotation() != HUNTING_AREA_ROTATION:
            # With no initial value the key is read at once: by a lambda.
            self.register(HUNTING_AREA, lambda: None)
            self.register(AREA_STRETCHES, lambda: None)
            self.register(AREA_PRESENCE, lambda: None)
            return
        world_map = self._world_map()
        area, origin = self._area(world_map)
        try:
            self._stretches = area.require_stretches(world_map)
        except EmptyHuntingArea as error:
            raise StartupRefused(
                f"{self}: {error}. Name a saved area that holds one with the "
                "profile's `hunting_area` setting, or draw one at launch."
            ) from error
        self._presence = PresenceCounter(area, self.data.clock)
        self.emit(ROTATION_AREA_SET, area_set_payload(world_map, area, origin))
        logger.info("%s hunts %s on map %s.", self, area, world_map.id)
        self.register(HUNTING_AREA, lambda: area, initial_value=area)
        self.register(
            AREA_STRETCHES,
            self._reachable_stretches,
            threshold=self.REFRESH,
            initial_value=self._stretches,
        )
        self.register(
            AREA_PRESENCE,
            self._presence_now,
            threshold=self.REFRESH,
            initial_value=NOBODY,
        )

    # --- setup's ---------------------------------------------------------------

    def _rotation(self) -> str:
        try:
            return rotation_name(self._rotation_settings)
        except ProfileError as error:
            raise StartupRefused(f"{self}: {error}") from error

    def _world_map(self) -> WorldMap:
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            raise StartupRefused(
                f"{self}: `rotation: hunting_area` hunts an area of the bot's map, "
                "and its map isn't known or has no minimap: name it with the "
                "profile's `map` setting."
            )
        return world_map

    def _area(self, world_map: WorldMap) -> tuple[HuntingArea, str]:
        """The area to hunt, and where it came from (`AreaSetPayload.origin`)."""
        if self._saved_name is not None:
            try:
                return load_area(world_map.id, self._saved_name, self.FOLDER), "profile"
            except UnknownHuntingArea as error:
                raise StartupRefused(
                    f"{self}: `hunting_area: {self._saved_name}`: {error}"
                ) from error
        return self._ask(world_map), "window"

    def _ask(self, world_map: WorldMap) -> HuntingArea:
        """The area the maintainer chooses in the launch window."""
        reader = self.read(MINIMAP_READER)
        canvas = None if reader is None else reader.canvas
        if canvas is None:
            raise StartupRefused(
                f"{self}: no minimap canvas to draw the Hunting Area on: name a "
                "saved area with the profile's `hunting_area` setting."
            )
        try:
            area = hunting_area_window.choose_hunting_area(
                world_map, canvas, self.FOLDER, self.read(HANDLE), self._live
            )
        except hunting_area_window.NoDisplay as error:
            raise StartupRefused(
                f"{self}: {error}, so the Hunting Area can't be drawn at launch: "
                "name a saved area with the profile's `hunting_area` setting."
            ) from error
        if area is None:
            raise StartupRefused(
                f"{self}: no Hunting Area was chosen in the launch window: draw "
                "one, or name a saved area with the profile's `hunting_area` "
                "setting."
            )
        return area

    def _live(self) -> hunting_area_window.LiveReading:
        """What the launch window shows live: one fresh read of the minimap."""
        world_map = self.read(WORLD_MAP)
        reader = self.read(MINIMAP_READER)
        if world_map is None or world_map.minimap is None or reader is None:
            return hunting_area_window.LiveReading()
        frame = self.refresh(FRAME)
        if not frame.ok:
            return hunting_area_window.LiveReading()
        view = reader.read(frame, markers=(ANOTHER,)).value
        return hunting_area_window.live_reading(view, world_map.minimap)

    # --- the update functions --------------------------------------------------

    def _reachable_stretches(self) -> tuple[Stretch, ...]:
        """
        The area's stretches on the Platforms a Path reaches from the
        character; every stretch while that isn't known, or when none is.
        """
        # Imported here: the pathing module imports the destination one, which
        # reads these keys.
        from .pathing import reachable_platforms

        among = reachable_platforms(self.data)
        if among is None:
            return self._stretches
        found = tuple(s for s in self._stretches if s.platform in among)
        if found:
            self._unreachable_logged = False
            return found
        if not self._unreachable_logged:
            self._unreachable_logged = True
            logger.error(
                "%s: no stretch of the Hunting Area is on a Platform a Path "
                "reaches from the character; every stretch is kept.",
                self,
            )
        return self._stretches

    def _presence_now(self) -> AreaPresence:
        assert self._presence is not None, "registered with an area only"
        reading = self.read(OTHER_PLAYERS)
        if reading is self._sampled:
            return self._presence.value
        self._sampled = reading
        stretches = self.read(AREA_STRETCHES)
        assert stretches is not None, "registered with an area only"
        return self._presence.sample(reading, stretches)


#: The Hunting Area the rotation hunts; None when the rotation is not
#: `hunting_area`. Resolved once, at start.
HUNTING_AREA: Key[HuntingArea | None] = Key("hunting_area", HuntingAreaProvider)
#: Where in the area the character may go: its stretches on the Platforms a Path
#: reaches; None when the rotation is not `hunting_area`.
AREA_STRETCHES: Key[tuple[Stretch, ...] | None] = Key(
    "area_stretches", HuntingAreaProvider
)
#: Whether someone has settled in the area, who is near, and how much is left to
#: go for; None when the rotation is not `hunting_area`.
AREA_PRESENCE: Key[AreaPresence | None] = Key("area_presence", HuntingAreaProvider)


def area_set_payload(
    world_map: WorldMap, area: HuntingArea, origin: str
) -> AreaSetPayload:
    """`rotation.area_set`'s payload."""
    return {
        "map_id": int(world_map.id),
        "left": int(area.left),
        "top": int(area.top),
        "right": int(area.right),
        "bottom": int(area.bottom),
        "name": area.name,
        "origin": origin,
    }
