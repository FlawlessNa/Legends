import cv2
import numpy as np
import os
import string
from paths import ROOT
from botting.visuals import InGameDynamicVisuals
from botting.utilities import (
    Box,
    take_screenshot,
)


class InventoryMenu(InGameDynamicVisuals):
    """
    Implements the in-game Inventory menu.
    """

    _menu_icon_detection_needle: np.ndarray = cv2.imread(
        os.path.join(ROOT, "royals/assets/detection_images/inventory_menu.png")
    )
    _slot_color: np.ndarray = np.array([221, 238, 238])
    _active_tab_color: np.ndarray = np.array([136, 102, 238])
    _empty_slot_rect_width: int = 31
    _empty_slot_rect_height: int = 31
    _emtpy_slot_cnt_area: int = 900
    total_slots: int = 96
    tabs: tuple = ("Equip", "Use", "Setup", "Etc", "Cash")

    mesos_box: Box = Box(
        left=22,
        right=35,
        top=262,
        bottom=262,
        name="Mesos Box",
        offset=True,
        config=f"--psm 7 -c tessedit_char_whitelist=,{string.digits}",
    )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        return cv2.resize(image, None, fx=10, fy=10)

    def is_displayed(self, handle: int, image: np.ndarray = None) -> bool:
        return True if self._menu_icon_position(handle, image) is not None else False

    def is_extended(self, handle: int, image: np.ndarray = None) -> bool:
        if image is None:
            image = take_screenshot(handle)
        if not self.is_displayed(handle, image):
            return False

        processed = cv2.inRange(image, self._slot_color, self._slot_color)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        def _filter(cnt) -> bool:
            x, y, w, h = cv2.boundingRect(cnt)
            cond1 = (
                self._empty_slot_rect_height - 1
                <= h
                <= self._empty_slot_rect_height + 1
            )
            cond2 = (
                self._empty_slot_rect_width - 1 <= w <= self._empty_slot_rect_width + 1
            )
            return cond1 and cond2

        if len(list(filter(_filter, contours))) > 24:
            return True
        return False

    def get_current_mesos(self, handle: int, image: np.ndarray = None) -> str:
        if image is None:
            image = take_screenshot(handle, self.get_abs_box(handle, self.mesos_box))
        return self.read_from_img(image, self.mesos_box.config)

    def get_active_tab(self, handle: int, image: np.ndarray = None) -> str | None:
        if image is None:
            image = take_screenshot(handle)
        if not self.is_displayed(handle, image):
            return

        menu_pos = self._menu_icon_position(handle, image)

        processed = cv2.inRange(image, self._active_tab_color, self._active_tab_color)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        largest = max(contours, key=cv2.contourArea)
        rect = cv2.boundingRect(largest)
        center = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)

        horizontal_distance = center[0] - menu_pos.center[0]
        if horizontal_distance < -35:
            return "Equip"
        elif -35 <= horizontal_distance < -1:
            return "Use"
        elif -1 <= horizontal_distance < 33:
            return "Setup"
        elif 33 <= horizontal_distance < 67:
            return "Etc"
        elif 67 <= horizontal_distance:
            return "Cash"

    def get_tab_count(self, current: str, target: str) -> int:
        """
        Returns the number of tabs between the current tab and the target tab.
        :param current:
        :param target:
        :return:
        """
        if current == target:
            return 0
        return (self.tabs.index(target) - self.tabs.index(current)) % len(self.tabs)

    def get_space_left(self, handle: int, image: np.ndarray = None) -> int | None:
        """
        Returns the number of empty slots in the inventory.
        Only works when inventory is displayed and extended.
        :param handle:
        :param image:
        :return:
        """
        if image is None:
            image = take_screenshot(handle)
        if not self.is_extended(handle, image):
            return

        processed = cv2.inRange(image, self._slot_color, self._slot_color)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        def _filter(cnt) -> bool:
            x, y, w, h = cv2.boundingRect(cnt)
            cond1 = (
                self._empty_slot_rect_height - 1
                <= h
                <= self._empty_slot_rect_height + 1
            )
            cond2 = (
                self._empty_slot_rect_width - 1 <= w <= self._empty_slot_rect_width + 1
            )
            cond3 = (
                self._emtpy_slot_cnt_area - 10
                <= cv2.contourArea(cnt)
                <= self._emtpy_slot_cnt_area + 10
            )
            return cond1 and cond2 and cond3

        return len(list(filter(_filter, contours)))
