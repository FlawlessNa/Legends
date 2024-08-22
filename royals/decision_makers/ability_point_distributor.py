import logging
import multiprocessing.connection
import multiprocessing.managers
import numpy as np

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, ActionWithValidation, BotData, DecisionMaker
from royals.actions import ensure_ability_menu_displayed
from royals.actions import priorities
from .mixins import (
    MenusMixin,
    UIMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class AbilityPointDistributor(MenusMixin, UIMixin, DecisionMaker):
    CONFIG_KEY = "Ability Menu"
    _throttle = 30.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._ap_menu_key = controller.key_binds(self.data.ign)[self.CONFIG_KEY]
        self.condition = self.request_proxy(self.metadata, f"{self}", "Condition")
        self._create_ap_menu_attributes(self.condition)
        self._create_ui_attributes()
        self._prev_level_img = self.data.current_level_img.copy()

    async def _decide(self) -> None:
        self.data.update_attribute("current_level_img")

        if not np.array_equal(self.data.current_level_img, self._prev_level_img):
            logger.log(LOG_LEVEL, f"Level up detected for {self.data.ign}.")
            ensure_ability_menu_displayed(
                **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition)
            )
            self.data.update_attribute("available_ap")

            if self.data.available_ap > 0:
                logger.log(LOG_LEVEL, f"{self} now distributing AP.")
                self._distribute_ap(self.data.available_ap)
                ensure_ability_menu_displayed(
                    **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition),
                    ensure_displayed=False,
                )
            else:
                logger.log(LOG_LEVEL, f"Uh-oh. {self} has no AP to distribute.")
                ensure_ability_menu_displayed(
                    **self._display_kwargs("Ability Menu Trigger", 2.0, self.condition),
                    ensure_displayed=False,
                )

        self._prev_level_img = self.data.current_level_img.copy()

    def _distribute_ap(self, num_points: int) -> None:
        target = self.data.ability_menu.stat_mapper[self.data.character.main_stat]
        request = ActionRequest(
            "Distributing AP",
            controller.mouse_move_and_click,
            self.data.ign,
            priorities.AP_DISTRIBUTION,
            args=(self.data.handle, target.center),
            kwargs={"nbr_times": num_points},
        )
        validated_action = ActionWithValidation(
            self.pipe,
            lambda: self.data.ability_menu.get_available_ap(
                self.data.handle, self.data.current_client_img
            )
            == 0,
            self.condition,
            5.0,
        )
        validated_action.execute_blocking(request)
