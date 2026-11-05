import logging
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, ActionWithValidation, BotData, DecisionMaker
from botting.screen import Status
from botting.utilities import CLIENT_HORIZONTAL_MARGIN_PX, CLIENT_VERTICAL_MARGIN_PX
from maple.actions import ensure_ability_menu_displayed, priorities
from maple.screen.status_bar import STATUS_BAR

from .mixins import (
    MenusMixin,
    UIMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class AbilityPointDistributor(MenusMixin, UIMixin, DecisionMaker):
    CONFIG_KEY = "Ability Menu"
    screen_readers = (STATUS_BAR,)
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
            self.data.update_attribute("available_ap")

            if self.data.available_ap > 0:
                logger.info("%s now distributing AP.", self)
                self._disable_decision_makers("Rotation")
                self._distribute_ap(self.data.available_ap)
                ensure_ability_menu_displayed(
                    **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition),
                    ensure_displayed=False,
                )
                self._enable_decision_makers("Rotation")
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

    def _distribute_ap(self, num_points: int) -> None:
        target = self.data.ability_menu.stat_mapper[self.data.character.main_stat]
        target = self.data.ability_menu.get_abs_box(self.data.handle, target)
        # The old readers' boxes carry the margins `find_image` adds; the mouse
        # takes client-area points. Both go with the old readers in #316.
        x, y = target.center
        point = (x - CLIENT_HORIZONTAL_MARGIN_PX, y - CLIENT_VERTICAL_MARGIN_PX)

        request = ActionRequest(
            "Distributing AP",
            controller.mouse_move_and_click,
            self.data.ign,
            priorities.AP_DISTRIBUTION,
            args=(self.data.handle, point),
            block_lower_priority=True,
            kwargs={"nbr_times": num_points, "delay": 0.15},
        )
        validated_action = ActionWithValidation(
            self.pipe,
            lambda: (
                self.data.ability_menu.get_available_ap(
                    self.data.handle, self.data.current_client_img
                )
                == 0
            ),
            self.condition,
            60.0,
            correlation_id=self.correlation_id,
        )
        validated_action.execute_blocking(request)
