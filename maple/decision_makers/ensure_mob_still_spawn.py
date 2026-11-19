import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from collections.abc import Callable

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker, Provider
from botting.screen import Status
from maple.actions import priorities, toggle_menu
from maple.model.navigation import Point
from maple.screen.chat import CHAT
from maple.telemetry_events import (
    RECOVERY_MOB_SPAWN_RESTORED,
    MobSpawnRestoredPayload,
)

from .mob_detection import mob_count_in_img
from .mobs_hitting import MobsHitting
from .providers import (
    AREA_STRETCHES,
    CHAT_SHOWN,
    DESTINATION,
    FRAME,
    HANDLE,
    MOBS,
    wander,
    wander_in_area,
)
from .reactions import Reactions
from .rotation import Rotation
from .telecast_mobs_hitting import TelecastMobsHitting

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class CheckMobsStillSpawn(DecisionMaker):
    """
    Checks, every 3 s, that mobs still spawn around the character.

    When fewer than `mob_spawn_alert_threshold` have been seen for
    `mob_spawn_alert_timer` seconds, it takes over, as an ordinary DecisionMaker
    holding a Pause and a Claim (ADR 0004): mob hitting is paused, the chat is
    hidden, and the character wanders the map's platforms (a Claim on
    `DESTINATION` with `wander`), or the Hunting Area's stretches when there is
    one (`AREA_STRETCHES`, with `wander_in_area`), until enough mobs show up
    again. Then the chat
    is shown again, and both are handed back as the blocks exit, by any route.

    When they do not show up within `FAILSAFE_TIMER`, it stops the bot until the
    user sends Discord `RESUME`, and reacts in the chat as a player would.
    """

    _throttle = 3.0
    FAILSAFE_TIMER = 30.0
    screen_readers = (CHAT,)
    reads = (FRAME, MOBS, HANDLE, CHAT_SHOWN, AREA_STRETCHES, *Reactions.reads)
    steers = (DESTINATION,)
    pauses = (
        MobsHitting,
        TelecastMobsHitting,
        Rotation,
        "maple.decision_makers.ensure_mob_still_spawn.CheckMobsStillSpawn",
        "maple.decision_makers.ensure_still_in_map.CheckStillInMap",
    )

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        mob_spawn_alert_timer: float,
        mob_spawn_alert_threshold: int,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._alert_timer = mob_spawn_alert_timer
        self._alert_threshold = mob_spawn_alert_threshold
        self._last_valid_detection = time.perf_counter() + 30.0
        self._reactions = Reactions(self)

    def setup(self) -> None:
        self._condition = self._proxies.instance(repr(self), "Condition")

    def on_start(self) -> None:
        self._last_valid_detection = time.perf_counter() + 10.0

    async def _decide(self) -> None:
        mob_count = self._mob_count(debug=True)

        # Enough mobs, reset timer
        if mob_count >= self._alert_threshold:
            self._last_valid_detection = time.perf_counter()

        # Not enough mobs and timer expired
        elif time.perf_counter() - self._last_valid_detection >= self._alert_timer:
            logger.warning("No mobs detected in %s seconds.", self._alert_timer)
            await self._failsafe()

    async def _failsafe(self) -> None:
        """
        Pause mob hitting, hide the chat and wander until mobs show up, within
        `FAILSAFE_TIMER`; then show the chat. Whatever ends it, mob hitting and
        the destination are handed back as its blocks exit. A step that times
        out stops the bot for the user instead (`_give_up`), before they do.
        """
        async with self.pause(
            MobsHitting,
            TelecastMobsHitting,
            reason=f"no mobs for {self._alert_timer} s",
        ):
            try:
                await self._validate_request_async(
                    self._toggle_chat_request(),
                    lambda: self._chat_shown() is False,
                    timeout=5.0,
                )
                # Wander the map's platforms until mobs show up: a new random
                # destination each time the current one is reached (#398). A
                # `game_data` map has no feature cycle to walk instead. With a
                # Hunting Area, its stretches only (#571).
                async with self.claim(
                    DESTINATION, self._wander(), reason="wander until mobs spawn"
                ):
                    await asyncio.wait_for(
                        self._failsafe_procedure(), timeout=self.FAILSAFE_TIMER
                    )
                    restored: MobSpawnRestoredPayload = {
                        "alert_timer": float(self._alert_timer),
                        "alert_threshold": int(self._alert_threshold),
                    }
                    self.emit(RECOVERY_MOB_SPAWN_RESTORED, restored)
                    await self._validate_request_async(
                        self._toggle_chat_request(),
                        lambda: self._chat_shown() is True,
                        timeout=5.0,
                    )
                    self._last_valid_detection = time.perf_counter()
            except TimeoutError:
                self._give_up()

    def _wander(self) -> Callable[[Provider], Point]:
        """
        The source to wander with: the Hunting Area's stretches when there is an
        area (`wander_in_area`), the map's platforms otherwise (`wander`).
        """
        return wander if self.read(AREA_STRETCHES) is None else wander_in_area

    def _give_up(self) -> None:
        """
        The failsafe failed: stop the bot until the user sends Discord `RESUME`,
        and send a final chat reaction.

        Mob hitting is paused for the user too, before the failsafe's own Pause
        on it is released: the legacy disable it replaces left it disabled until
        `RESUME`.
        """
        self.pause_for_user(
            Rotation,
            CheckMobsStillSpawn,
            _check_still_in_map(),
            MobsHitting,
            TelecastMobsHitting,
            reason="mobs did not spawn again",
        )
        self._reactions.react("advanced")
        logger.critical(
            "Failed to ensure mobs still spawn after %s seconds",
            self.FAILSAFE_TIMER,
        )

    async def _failsafe_procedure(self) -> None:
        try:
            await asyncio.wait_for(
                self._rotate_until_mobs_detected(), timeout=self.FAILSAFE_TIMER // 2
            )
        except TimeoutError:
            # Still no mobs.
            self._reactions.react("light")
            logger.warning(
                "No mobs detected after %s seconds", self.FAILSAFE_TIMER // 2
            )

            # Keep trying until this is cancelled by the failsafe procedure
            await self._rotate_until_mobs_detected()

    async def _rotate_until_mobs_detected(self) -> None:
        while True:
            mob_count = self._mob_count(debug=False)
            logger.debug("%s sees %s mob(s).", self.data.ign, mob_count)
            if mob_count >= self._alert_threshold:
                break
            await asyncio.sleep(0.5)

    def _mob_count(self, *, debug: bool) -> int:
        """How many of the map's mobs the current frame shows."""
        return mob_count_in_img(
            self.read(FRAME).pixels,
            self.read(MOBS),
            self.read(HANDLE),
            debug=debug,
        )

    def _chat_shown(self) -> bool | None:
        """
        Whether the chat log is shown in a fresh frame (`CHAT_SHOWN`); `None`
        when that can't be read (covered, or an unusable frame), which neither
        validation accepts.
        """
        self.refresh(FRAME)
        reading = self.refresh(CHAT_SHOWN)
        if reading.status is not Status.READ:
            logger.debug(
                "%s can't tell whether the chat is shown: %s (%s)",
                self,
                reading.status.value,
                reading.detail,
            )
            return None
        return reading.value

    def _toggle_chat_request(self) -> ActionRequest:
        return ActionRequest(
            f"{self} - Toggle Chat",
            toggle_menu,
            self.data.ign,
            priorities.ANTI_DETECTION,
            block_lower_priority=True,
            args=(self.read(HANDLE), self.data.ign, "Chat Toggle"),
        )


def _check_still_in_map() -> type[DecisionMaker]:
    """`CheckStillInMap`, which imports this module, so it is imported here."""
    from .ensure_still_in_map import CheckStillInMap

    return CheckStillInMap
