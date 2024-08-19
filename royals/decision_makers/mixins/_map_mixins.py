import logging
import multiprocessing.connection
import multiprocessing.managers

from royals.actions import ensure_minimap_displayed, toggle_minimap
from botting import PARENT_LOG
from botting.core import ActionRequest, ActionWithValidation, BotData, DecisionMaker

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class MinimapAttributesMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection
    MINIMAP_POS_REFRESH_RATE = 0.1
    ERROR_HANDLING_TIME_LIMIT = 5.0

    def _get_minimap_pos(self) -> tuple[int, int]:
        return self.data.current_minimap.get_character_positions(
            self.data.handle,
            client_img=self.data.current_client_img,
            map_area_box=self.data.current_minimap_area_box,
        ).pop()

    def _minimap_pos_error_handler(self) -> None:
        """
        Blocks the current Bot (& Engine) until the current_minimap_position the handler
        had time to attempt fixing the issue uninterrupted by other tasks.
        :return:
        """
        identifier = f"{self}.current_minimap_position Error Handler"
        logger.warning(f"{identifier} Attempt")
        condition = DecisionMaker.request_proxy(
            self.metadata,
            identifier,
            "Condition",
        )

        ensure_minimap_displayed(
            identifier,
            self.data.handle,
            self.data.ign,
            self.pipe,
            self.data.current_minimap,
            condition,
            self.ERROR_HANDLING_TIME_LIMIT,
        )

        # TODO - Add Mouse not interfering
        ensure_mouse_not_on_minimap(identifier, ...)
        self.data.update_attribute("current_client_img")
        self.data.update_attribute("minimap_currently_displayed")
        self.data.update_attribute("current_minimap_state")
        self.data.update_attribute("current_minimap_area_box")
        self.data.update_attribute("current_entire_minimap_box")
        self.data.update_attribute("current_minimap_position")

    def _create_minimap_attributes(self) -> None:
        self.data.create_attribute(
            "minimap_currently_displayed",
            lambda: self.data.current_minimap.is_displayed(
                self.data.handle, self.data.current_client_img
            ),
        )
        self.data.create_attribute(
            "current_minimap_state",
            lambda: self.data.current_minimap.get_minimap_state(
                self.data.handle, self.data.current_client_img
            ),
        )
        self.data.create_attribute(
            "current_minimap_area_box",
            lambda: self.data.current_minimap.get_map_area_box(
                self.data.handle,
                self.data.current_client_img,
            ),
        )
        self.data.create_attribute(
            "current_minimap_position",
            self._get_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
            error_handler=self._minimap_pos_error_handler,
        )
        self.data.create_attribute(
            "current_entire_minimap_box",
            lambda: self.data.current_minimap.get_entire_minimap_box(
                self.data.handle, self.data.current_client_img
            ),
        )
