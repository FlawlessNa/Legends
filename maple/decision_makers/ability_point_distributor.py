import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, ActionWithValidation, BotData, DecisionMaker
from botting.screen import Status, frame_source
from botting.utilities import Box
from maple.actions import click_then_move_off, ensure_ability_menu_displayed, priorities
from maple.screen.stat_window import STAT_WINDOW
from maple.screen.status_bar import STATUS_BAR

from .mixins import (
    MenusMixin,
    UIMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class AbilityPointDistributor(MenusMixin, UIMixin, DecisionMaker):
    CONFIG_KEY = "Ability Menu"
    screen_readers = (STATUS_BAR, STAT_WINDOW)
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
        self.condition = self._proxies.instance(repr(self), "Condition")
        self._create_ap_menu_attributes(self.condition)
        self._create_status_bar_attributes()
        self._unreadable: str | None = None
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
            self.data.update_attributes("current_frame", "stat_window")
            reading = self.data.stat_window

            # AP is spent only on a `READ`: a covered or unsure window is never
            # taken for an AP, nor for none.
            if reading.status is Status.READ and reading.value.available_ap > 0:
                logger.info("%s now distributing AP.", self)
                self._disable_decision_makers("Rotation")
                self._distribute_ap(
                    reading.value.available_ap,
                    reading.value.up_buttons[self.data.character.main_stat],
                    reading.value.bounds,
                )
                self._close_menu()
                self._enable_decision_makers("Rotation")
            else:
                if reading.status is Status.READ:
                    logger.warning("Uh-oh. %s has no AP to distribute.", self)
                else:
                    logger.warning(
                        "%s can't read the AP (%s: %s); none distributed.",
                        self,
                        reading.status.name,
                        reading.detail,
                    )
                self._close_menu()

        if level is not None:
            self._prev_level = level

    def _close_menu(self) -> None:
        ensure_ability_menu_displayed(
            **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition),
            ensure_displayed=False,
        )

    def _level(self) -> int | None:
        """The level on the status bar now, or `None` when it can't be read."""
        self.data.update_attributes("current_frame", "status_bar")
        reading = self.data.status_bar
        if reading.status is not Status.READ:
            # Logged once per change, not on every decision.
            if self._unreadable != reading.detail:
                logger.warning("%s can't read the level: %s", self, reading.detail)
            self._unreadable = reading.detail
            return None
        self._unreadable = None
        return reading.value.level

    def _distribute_ap(
        self, num_points: int, button: tuple[int, int], window: Box
    ) -> None:
        """
        Click the main stat's +1 button, at `button` in client pixels, once per
        point, then move the cursor off the `window`, until a fresh read of the
        window shows no AP left. The cursor is moved off because the read
        needs every +1 button seen disabled to take an AP of 0 for one.
        """
        request = ActionRequest(
            "Distributing AP",
            click_then_move_off,
            self.data.ign,
            priorities.AP_DISTRIBUTION,
            args=(self.data.handle, button, window),
            block_lower_priority=True,
            kwargs={"nbr_times": num_points, "delay": 0.15},
        )
        validated_action = ActionWithValidation(
            self.pipe,
            self._no_ap_left,
            self.condition,
            60.0,
            correlation_id=self.correlation_id,
        )
        validated_action.execute_blocking(request)

    def _no_ap_left(self) -> bool:
        """Whether a fresh capture reads the window with an AP of 0."""
        reading = self.data.stat_window_reader.read(
            frame_source().grab(self.data.handle)
        )
        return reading.status is Status.READ and reading.value.available_ap == 0
