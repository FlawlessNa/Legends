import logging
import multiprocessing.connection
import multiprocessing.managers
import threading

from botting import PARENT_LOG, controller
from botting.core import (
    HANDLE,
    ActionRequest,
    ActionWithValidation,
    BotData,
    DecisionMaker,
)
from botting.screen import Status
from botting.utilities import CLIENT_HORIZONTAL_MARGIN_PX, CLIENT_VERTICAL_MARGIN_PX
from maple.actions import ensure_ability_menu_displayed, priorities
from maple.screen.status_bar import STATUS_BAR

from .providers import (
    ABILITY_MENU,
    AVAILABLE_AP,
    CHARACTER,
    FRAME,
    STATUS_BAR_READING,
)
from .rotation import Rotation

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class AbilityPointDistributor(DecisionMaker):
    """
    Spends the ability points a level-up gives, on the character's main stat.

    On a level read higher than the last one, it opens the ability menu, and
    while it clicks the points in it holds a Pause on `Rotation` (ADR 0004): the
    character doesn't walk off with the menu open, and the Pause is released as
    the block exits, by any route.
    """

    CONFIG_KEY = "Ability Menu"
    screen_readers = (STATUS_BAR,)
    reads = (FRAME, HANDLE, STATUS_BAR_READING, ABILITY_MENU, AVAILABLE_AP, CHARACTER)
    pauses = (Rotation,)
    _throttle = 30.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._ap_menu_key = controller.key_binds(self.data.ign)[self.CONFIG_KEY]
        self._unreadable: str | None = None
        self._prev_level: int | None = None

    def setup(self) -> None:
        self.condition = self._proxies.instance(repr(self), "Condition")
        self._prev_level = self._level()

    async def _decide(self) -> None:
        level = self._level()

        # A level that couldn't be read is not a level up, and doesn't replace
        # the last one read: the next readable level is compared with it.
        if (
            level is not None
            and self._prev_level is not None
            and level > self._prev_level
        ):
            logger.info("Level up detected for %s.", self.data.ign)
            ensure_ability_menu_displayed(
                **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition)
            )
            available_ap = self.refresh(AVAILABLE_AP) or 0

            if available_ap > 0:
                logger.info("%s now distributing AP.", self)
                async with self.pause(Rotation, reason="distributing AP"):
                    self._distribute_ap(available_ap)
                    ensure_ability_menu_displayed(
                        **self._display_kwargs(
                            "Ability Menu Trigger", 2.0, self.condition
                        ),
                        ensure_displayed=False,
                    )
            else:
                logger.warning("Uh-oh. %s has no AP to distribute.", self)
                ensure_ability_menu_displayed(
                    **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition),
                    ensure_displayed=False,
                )

        if level is not None:
            self._prev_level = level

    def _level(self) -> int | None:
        """The level on the status bar now, or `None` when it can't be read."""
        self.refresh(FRAME)
        reading = self.refresh(STATUS_BAR_READING)
        if reading.status is not Status.READ:
            # Logged once per change, not on every decision.
            if self._unreadable != reading.detail:
                logger.warning("%s can't read the level: %s", self, reading.detail)
            self._unreadable = reading.detail
            return None
        self._unreadable = None
        assert reading.value is not None, "a read status bar has its value"
        return reading.value.level

    def _display_kwargs(
        self, identifier: str, timeout: float, condition: threading.Condition
    ) -> dict:
        return {
            "identifier": identifier,
            "handle": self.read(HANDLE),
            "ign": self.data.ign,
            "pipe": self.pipe,
            "menu": self.read(ABILITY_MENU),
            "condition": condition,
            "timeout": timeout,
        }

    def _distribute_ap(self, num_points: int) -> None:
        menu = self.read(ABILITY_MENU)
        handle = self.read(HANDLE)
        target = menu.stat_mapper[self.read(CHARACTER).main_stat]
        target = menu.get_abs_box(handle, target)
        assert target is not None, "the ability menu is open: its boxes are placed"
        # The old readers' boxes carry the margins `find_image` adds; the mouse
        # takes client-area points. Both go with the ability menu in #314.
        x, y = target.center
        point = (x - CLIENT_HORIZONTAL_MARGIN_PX, y - CLIENT_VERTICAL_MARGIN_PX)

        request = ActionRequest(
            "Distributing AP",
            controller.mouse_move_and_click,
            self.data.ign,
            priorities.AP_DISTRIBUTION,
            args=(handle, point),
            block_lower_priority=True,
            kwargs={"nbr_times": num_points, "delay": 0.15},
        )
        validated_action = ActionWithValidation(
            self.pipe,
            lambda: menu.get_available_ap(handle, self.read(FRAME).pixels) == 0,
            self.condition,
            60.0,
            correlation_id=self.correlation_id,
        )
        validated_action.execute_blocking(request)
