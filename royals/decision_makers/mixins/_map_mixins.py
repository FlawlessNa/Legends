import logging
import multiprocessing.connection
import multiprocessing.managers
import win32gui

from royals.actions import ensure_minimap_displayed
from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from botting.utilities import Box, take_screenshot

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

        self._ensure_mouse_not_on_minimap(identifier)
        self.data.update_attributes(
            "current_client_img",
            "minimap_currently_displayed",
            "current_minimap_state",
            "current_minimap_area_box",
            "current_entire_minimap_box",
            "current_minimap_title_box",
            "current_minimap_position",
        )

    def _ensure_mouse_not_on_minimap(self, identifier: str) -> None:
        """
        Looks into the current_entire_minimap_box is currently known.
        If it is, set a mouse position target that is anywhere on the window except for
        the minimap.
        If not, the target is set to the center of the window (with small variation).
        # TODO - If other mouse functions are needed, crate a royals.action module instead.
        :param identifier:
        :return:
        """
        if getattr(self.data, "current_entire_minimap_box", None) is not None:
            region_to_avoid = self.data.current_entire_minimap_box
        else:
            # In this case, avoid the first "quadrant" of the window.
            region_to_avoid = Box(left=0, right=500, top=0, bottom=500)

        # Choose a random point on the window that is not on the minimap.
        left, top, right, bottom = win32gui.GetWindowRect(self.data.handle)
        width, height = right - left, bottom - top
        client_box = Box(left=0, right=width, top=0, bottom=height)
        while True:
            x, y = client_box.random()
            if (x, y) not in region_to_avoid:
                break

        request = ActionRequest(
            identifier,
            controller.mouse_move,
            self.data.ign,
            args=(self.data.handle, (x, y)),
        )
        self.pipe.send(request)

    def _create_minimap_attributes(self) -> None:
        ensure_minimap_displayed(
            f"{self} Initial Setup",
            self.data.handle,
            self.data.ign,
            self.pipe,
            self.data.current_minimap,
            DecisionMaker.request_proxy(
                self.metadata,
                f"{self} Initial Setup",
                "Condition",
            ),
            self.ERROR_HANDLING_TIME_LIMIT,
        )
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
            "current_entire_minimap_box",
            lambda: self.data.current_minimap.get_entire_minimap_box(
                self.data.handle, self.data.current_client_img
            ),
        )
        self.data.create_attribute(
            "current_minimap_title_box",
            lambda: self.data.current_minimap.get_minimap_title_box(
                self.data.handle, self.data.current_client_img
            ),
        ),
        self.data.create_attribute(
            "current_minimap_title_img",
            lambda: take_screenshot(
                self.data.handle, self.data.current_minimap_title_box
            ),
        )
        self.data.create_attribute(
            "current_minimap_position",
            self._get_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
            error_handler=self._minimap_pos_error_handler,
        )
        self.data.create_attribute("has_minimap_attributes", lambda: True)
