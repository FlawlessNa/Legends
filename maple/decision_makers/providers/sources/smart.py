"""
The `smart` destination source: towards the side most mobs are on.

The destination is drawn again once the character has stood within `ARRIVAL`
of it for `TIME_ON_TARGET`: towards the side most mobs are on, when enough are
around, else anywhere on its platform.
"""

from __future__ import annotations

import math
import statistics
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from botting.core import HANDLE, Key, StartupRefused
from maple.decision_makers.mob_detection import (
    get_mobs_positions_in_img,
    mobs_in_virtual_px,
)
from maple.decision_makers.providers.attacks import ATTACKS
from maple.decision_makers.providers.client import FRAME
from maple.decision_makers.providers.map import POSITION_FUSION, WORLD_MAP
from maple.decision_makers.providers.minimap import POSITION
from maple.decision_makers.providers.mobs import MOBS
from maple.decision_makers.providers.on_screen import ON_SCREEN_POSITION

if TYPE_CHECKING:
    from botting.screen import Frame
    from maple.decision_makers.providers.destination import DestinationProvider
    from maple.model.navigation import Point


class SmartSource:
    """
    Determines the next destination "the smart way". Uses the character's
    on-screen location to get a wide view of its platform. If there are mobs,
    the destination is the "average" position of those on the side where there
    are most, on the destination's platform. Otherwise, a random point on that
    platform.

    The smallest `min_mobs` of `ATTACKS` is how many mobs it steps towards: when
    that many are around, an attack would fire.
    """

    #: What it reads through the Provider: the window, the frame and the mobs
    #: to find them on it, the map, and the position with the camera it was
    #: read through.
    needs: ClassVar[tuple[Key[Any], ...]] = (
        HANDLE,
        FRAME,
        MOBS,
        WORLD_MAP,
        POSITION_FUSION,
        POSITION,
        ATTACKS,
    )

    #: Arrival, in virtual px: 4 minimap px.
    ARRIVAL = 64.0
    #: How far it steps towards the mobs at most, in virtual px: 10 minimap px.
    STEP = 160.0
    #: Seconds it stands on its destination before it draws the next.
    TIME_ON_TARGET = 0.75
    #: The fewest mobs it steps towards, whatever the profile says.
    MIN_MOBS_THRESHOLD = 2

    def __init__(self, provider: DestinationProvider) -> None:
        """
        :raises StartupRefused: The profile has no `attacks`.
        """
        attacks = provider.read(ATTACKS)
        if attacks is None:
            raise StartupRefused(
                f"{provider} rotates the smart way, and the profile has no "
                "attacks: list them, or rotate another way."
            )
        self.provider = provider
        #: The fewest mobs any attack fires at.
        self.mob_count_threshold: int = min(attack.min_mobs for attack in attacks)
        #: Whether the character has yet to be judged on its destination, and
        #: when it was.
        self._first_time_on_target = True
        self._last_target_reached_at = 0.0

    def next(self) -> Point:
        """
        The current destination until the character has stood within `ARRIVAL`
        of it for `TIME_ON_TARGET`, then the next one. An unsure position holds
        the destination.
        """
        provider = self.provider
        target = provider.checked_destination()
        reading = provider.position()
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.ARRIVAL:
            self._first_time_on_target = True
            return target

        # On target: has it been for longer than TIME_ON_TARGET?
        if self._first_time_on_target:
            provider.target_reached(position, target)
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return target
        elif time.perf_counter() - self._last_target_reached_at < self.TIME_ON_TARGET:
            return target

        # Reached once it has stood on target for longer than TIME_ON_TARGET.
        self._first_time_on_target = True
        # Check for mobs in the vicinity.
        provider.refresh(FRAME)
        on_screen_pos = self._on_screen_position()
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            frame = provider.read(FRAME)
            shape = frame.pixels.shape
            mask = np.zeros(shape, np.uint8)
            mask[
                max(0, y1 - 100) : min(shape[0], y2 + 100),
                max(0, x1 - 500) : min(shape[1], x2 + 500),
            ] = 255
            mobs_locations = get_mobs_positions_in_img(
                frame.pixels, provider.read(MOBS), provider.read(HANDLE), mask=mask
            )
            if len(mobs_locations) >= max(
                self.mob_count_threshold, self.MIN_MOBS_THRESHOLD
            ):
                stepped = self._step_towards_mobs(mobs_locations, frame, target)
                if stepped is not None:
                    return stepped

        platform = provider.destination_platform()
        if platform is None:
            return provider.random_point()
        return provider.world_map().random_point((platform,))

    def abandon(self) -> Point:
        """A fresh random point on a platform a Path reaches."""
        return self.provider.random_point()

    def _on_screen_position(self) -> tuple[int, int, int, int] | None:
        """
        Where the character was last found on screen, refreshed when stale, as
        `MobsHitting`, which reads `ON_SCREEN_POSITION`, has it. Not in `needs`:
        only this source looks at it, and a Bot that builds the Provider without
        hitting mobs (a calibration sitting) has no chat reader to find the
        character with. None when nothing reads it.
        """
        data = self.provider.data
        if not data.is_provided(ON_SCREEN_POSITION):
            return None
        last_known = data.peek(ON_SCREEN_POSITION)
        return data.read(ON_SCREEN_POSITION) or last_known

    def _step_towards_mobs(
        self, mobs: list[Sequence[int]], frame: Frame, target: Point
    ) -> Point | None:
        """
        A point on the destination's platform, towards the side most of `mobs`
        are on: their mean distance from the character, at most `STEP`. The mobs
        are placed in virtual px through the camera of the frame they were found
        on; None when that frame's camera or position isn't read, or the
        destination is on no platform.
        """
        provider = self.provider
        # Read on this frame, so its camera is the one that places the mobs.
        reading = provider.refresh(POSITION)
        fusion = provider.read(POSITION_FUSION)
        camera = None if fusion is None else fusion.camera
        platform = provider.world_map().platform_at(target)
        if camera is None or reading.value is None or platform is None:
            return None
        here = reading.value.x
        xs = [x for x, _ in mobs_in_virtual_px(mobs, frame.client_size, camera)]
        left = [here - x for x in xs if x < here]
        right = [x - here for x in xs if x >= here]
        if len(left) > len(right):
            x = max(here - min(statistics.mean(left), self.STEP), platform.left)
        else:
            x = min(here + min(statistics.mean(right), self.STEP), platform.right)
        y = platform.y_at(x)
        return None if y is None else (x, y)
