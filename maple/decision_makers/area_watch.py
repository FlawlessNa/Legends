"""
`AreaWatch`: tells the maintainer when another player settles in the Hunting
Area, and stands the character by when nothing in the area is left to go for
(#571, spec section 9).

It reads `AREA_PRESENCE` (`providers/hunting_area.py`), which says whether
someone has **Settled** (`CONTEXT.md`) and how much of the area is left, once a
second, and does three things:

- **Someone settles.** A Discord alert with the whole game window, and one
  `area.player_settled` record. The character keeps hunting. **[D8]** From then
  until settled ends, `AreaWatch` holds a Pause on `CheckMobsStillSpawn`: few
  mobs are explained by the other player, and the maintainer has been alerted,
  so the failsafe must not pause mob hitting and type in the chat beside them.
  The Pause is released when settled ends, and when `AreaWatch` is cancelled.
- **Nothing is left to go for.** When `free_share` has been 0 for
  `STAND_BY_AFTER`, a second alert rides on an Action that releases the movement
  keys and cancels `Rotation`'s Action in flight (as Movement recovery's
  Escalate does), `area.stand_by` is emitted, and `Rotation` and
  `CheckMobsStillSpawn` are paused until Discord `RESUME`. `MobsHitting` is not
  paused: the character still hits whatever comes into its reach. `AreaWatch`
  is not paused either, since it has to say when they leave. It never asks
  whether `RESUME` came: it stands by again only once `free_share` has risen
  above 0 and then been 0 for `STAND_BY_AFTER` again.
- **Settled ends.** A last message and `area.player_left`; when it stood by
  since they settled, the message adds that `RESUME` may be needed.

The release of the movement keys at stand-by is the only input it ever sends.
Nothing here pauses, delays or cancels a cast. With no `configs/discord.ini`,
no Discord request is sent and everything else happens.

The telemetry carries counts only: no name, no position, no chat line of another
player. The alert's picture is the game window, and goes to Discord alone.
"""

import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final

from botting import PARENT_LOG, controller
from botting.core import (
    ActionRequest,
    BotData,
    DecisionMaker,
    DiscordRequest,
    action_name,
)
from maple.actions import priorities
from maple.telemetry_events import (
    AREA_PLAYER_LEFT,
    AREA_PLAYER_SETTLED,
    AREA_STAND_BY,
    AreaWatchPayload,
)
from paths import ROOT

from .ensure_mob_still_spawn import CheckMobsStillSpawn
from .providers import AREA_PRESENCE, FRAME, HANDLE
from .providers.hunting_area import AreaPresence
from .rotation import Rotation

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

DISCORD_CONFIG = Path(ROOT) / "configs" / "discord.ini"
"""Where Discord is configured; without it the alerts are logged, not sent."""

STAND_BY_AFTER: Final = 180.0
"""Seconds `free_share` must stay 0, without a break, before the character
stands by. A starting value, tuned from what live Sessions show."""

DECIDES_EVERY: Final = 1.0
"""Seconds between two decisions."""

SETTLED_REASON: Final = "someone has settled in the Hunting Area"
"""Why `CheckMobsStillSpawn` is paused while someone has settled."""


class AreaWatch(DecisionMaker):
    """
    Watches who has settled in the Hunting Area. Run by `TrainingBot` only when
    the rotation is `hunting_area`; see the module docstring.
    """

    _throttle = DECIDES_EVERY
    reads = (AREA_PRESENCE, FRAME, HANDLE)
    pauses = (Rotation, CheckMobsStillSpawn)
    cancels = (Rotation,)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        discord_config: Path = DISCORD_CONFIG,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        **kwargs: object,
    ) -> None:
        """
        :param discord_config: The file whose presence turns Discord on.
        :param clock: Seconds, monotonic: times the stand-by.
        :param sleep: Waits a second between two reads while someone is settled.
        """
        super().__init__(metadata, data, pipe)
        self._discord_config = discord_config
        self._clock = clock
        self._sleep = sleep
        self._discord = False
        #: Whether the settled alert went, and its end has not been told yet.
        #: Kept when `AreaWatch` is paused and resumed, so it is not told twice.
        self._told = False
        #: Whether the character stood by since they settled.
        self._stood_by = False
        #: When `free_share` last became 0, None while it is above 0.
        self._crowded_since: float | None = None
        #: Whether it stood by for the crowding in progress.
        self._stood_by_here = False

    def setup(self) -> None:
        self._discord = self._discord_config.is_file()

    async def _decide(self) -> None:
        presence = self.read(AREA_PRESENCE)
        if presence is not None and presence.settled:
            await self._while_settled(presence)
        elif self._told:
            self._left(presence)

    async def _while_settled(self, presence: AreaPresence) -> None:
        """
        Hold the Pause on `CheckMobsStillSpawn` for as long as they are settled.
        It is released as the block exits: when settled ends, and when this
        decision is cancelled, by any route.
        """
        async with self.pause(CheckMobsStillSpawn, reason=SETTLED_REASON):
            if not self._told:
                self._settled(presence)
            current: AreaPresence | None = presence
            while current is not None and current.settled:
                self._count_crowding(current)
                await self._sleep(DECIDES_EVERY)
                current = self.read(AREA_PRESENCE)
        self._left(current)

    # --- what it does ------------------------------------------------------------

    def _settled(self, presence: AreaPresence) -> None:
        self._told = True
        self._stood_by = False
        self.emit(AREA_PLAYER_SETTLED, _payload(presence))
        logger.warning(
            "%s: someone settled in the Hunting Area (%d other player(s) inside).",
            self.data.ign,
            presence.inside,
        )
        self._alert(
            f"{self.data.ign}: someone has settled in the Hunting Area. The "
            "character keeps hunting the rest of it."
        )

    def _count_crowding(self, presence: AreaPresence) -> None:
        """Stand by once `free_share` has been 0 for `STAND_BY_AFTER`."""
        if presence.free_share > 0:
            self._crowded_since = None
            self._stood_by_here = False
            return
        now = self._clock()
        if self._crowded_since is None:
            self._crowded_since = now
        if self._stood_by_here or now - self._crowded_since < STAND_BY_AFTER:
            return
        self._stand_by(presence)

    def _stand_by(self, presence: AreaPresence) -> None:
        self._stood_by = True
        self._stood_by_here = True
        self.emit(AREA_STAND_BY, _payload(presence))
        logger.warning(
            "%s: nothing is left to go for in the Hunting Area; standing by.",
            self.data.ign,
        )
        ign = self.data.ign
        self.send(
            ActionRequest(
                f"{self} - Stand by",
                _release_movement_keys,
                ign=ign,
                priority=priorities.FAILSAFE,
                requeue_if_not_scheduled=True,
                cancels_itself=True,
                cancel_tasks=[action_name(Rotation, ign)],
                discord_request=self._discord_request(
                    f"{ign}: nothing is left to go for in the Hunting Area, so "
                    "the character is standing by with its keys released. It "
                    "still hits what comes into its reach. Send RESUME to "
                    "hunt again."
                ),
                args=(self.read(HANDLE),),
            )
        )
        self.pause_for_user(
            Rotation,
            CheckMobsStillSpawn,
            reason="no part of the Hunting Area is left to go for",
        )

    def _left(self, presence: AreaPresence | None) -> None:
        stood_by = self._stood_by
        self._told = False
        self._stood_by = False
        self._crowded_since = None
        self._stood_by_here = False
        self.emit(AREA_PLAYER_LEFT, _payload(presence))
        logger.warning("%s: the player who settled has left.", self.data.ign)
        message = (
            f"{self.data.ign}: the player who settled in the Hunting Area has left"
        )
        if stood_by:
            message += "; send `RESUME` if the bot is still standing by"
        message += "."
        self._alert(message)

    # --- Discord -----------------------------------------------------------------

    def _discord_request(self, message: str) -> DiscordRequest | None:
        """The message with the whole game window, or None with Discord off."""
        if not self._discord:
            return None
        return DiscordRequest(message, self.refresh(FRAME).pixels)

    def _alert(self, message: str) -> None:
        """An Action whose whole purpose is the Discord alert; none with Discord
        off. It blocks nothing and cancels nothing."""
        request = self._discord_request(message)
        if request is None:
            return
        self.send(
            ActionRequest(
                f"{self} - Area alert",
                _noop,
                ign=self.data.ign,
                priority=priorities.ANTI_DETECTION,
                cancels_itself=True,
                discord_request=request,
            )
        )


def _payload(presence: AreaPresence | None) -> AreaWatchPayload:
    """How many other players are inside, and `free_share`; counts only."""
    if presence is None:
        return {"inside": 0, "free_share": 1.0}
    return {"inside": presence.inside, "free_share": presence.free_share}


async def _release_movement_keys(handle: int) -> None:
    """The one input `AreaWatch` sends, run in Main Process."""
    controller.release_keys(["left", "up", "down", "right"], handle)


async def _noop() -> None:
    """An Action whose whole purpose is the Discord alert riding on it."""
