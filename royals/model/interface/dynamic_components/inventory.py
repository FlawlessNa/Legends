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
    _active_tab_color_lower: np.ndarray = np.array([136, 102, 238])
    _active_tab_color_upper: np.ndarray = np.array([187, 170, 255])
    _item_title_low_color: np.ndarray = np.array([140, 140, 140])
    _item_title_high_color: np.ndarray = np.array([255, 255, 255])
    _empty_slot_rect_width: int = 31
    _empty_slot_rect_height: int = 31
    _emtpy_slot_cnt_area: int = 900
    total_slots: int = 96
    _entire_inventory_box: Box = Box(left=2, right=492, top=45, bottom=233, offset=True)
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
    extend_button: Box = Box(
        left=119,
        right=31,
        top=3,
        bottom=-3,
        name="Extend Button",
        offset=True,
    )
    merge_and_sort_button: Box = ...

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        return cv2.resize(processed, None, fx=10, fy=10)

    def is_displayed(self, handle: int, image: np.ndarray = None) -> bool:
        return self._menu_icon_position(handle, image) is not None

    def is_extended(self, handle: int, image: np.ndarray = None) -> bool:
        if image is None:
            image = take_screenshot(handle)
        if not self.is_displayed(handle, image):
            return False

        processed = cv2.inRange(image, self._slot_color, self._slot_color)

        # 30000 is generally sufficient such that even when inventory is full, there are still
        # more than 30000 pixels that are the same color as the slots.
        if np.count_nonzero(processed) > 20000:
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
        buffer = Box(left=0, right=100, top=0, bottom=30)
        target = (menu_pos + buffer).extract_client_img(image)

        processed = cv2.inRange(
            target, self._active_tab_color_lower, self._active_tab_color_upper
        )
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if len(contours) > 0:
            largest = max(contours, key=cv2.contourArea)
            rect = cv2.boundingRect(largest)
            center = (rect[0] + rect[2] // 2, rect[1] + rect[3] // 2)

            horizontal_distance = center[0] - (menu_pos.width // 2)
            if horizontal_distance < -16:
                return "Equip"
            elif -16 <= horizontal_distance < 18:
                return "Use"
            elif 18 <= horizontal_distance < 52:
                return "Setup"
            elif 52 <= horizontal_distance < 86:
                return "Etc"
            elif 86 <= horizontal_distance:
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

    def get_all_slots_boxes(self, handle: int, image: np.ndarray = None) -> list[Box]:
        """
        Returns a list of all boxes in the inventory.
        :param handle:
        :param image:
        :return:
        """
        result = []
        if image is None:
            image = take_screenshot(handle)
        if not self.is_extended(handle, image):
            return

        inventory_box = self.get_abs_box(handle, self._entire_inventory_box)

        def x_offset(n: int) -> int:
            return 1 + n * (32 + 4) + n // 4 * 5

        def y_offset(n: int) -> int:
            return 1 + n * (32 + 2)

        return [
            Box(
                left=inventory_box.left + x_offset(x),
                right=inventory_box.left + 30 + x_offset(x),
                top=inventory_box.top + y_offset(y),
                bottom=inventory_box.top + 30 + y_offset(y),
            )
            for x in range(16)
            for y in range(6)
        ]

    def read_item_name(self, handle: int, mouse_pos: tuple[int, int]) -> str:
        """
        Given the current mouse position (and assuming it is on an item in
        the inventory), returns the name of the item.
        :param handle:
        :param mouse_pos:
        :return:
        """
        box = Box(
            left=mouse_pos[0] + 14,
            right=mouse_pos[0] + 230,
            top=mouse_pos[1] + 30,
            bottom=mouse_pos[1] + 50,
        )
        image = take_screenshot(handle, box)
        cv2.imshow("test", image)
        import time

        start = time.time()
        processed = cv2.inRange(
            image, self._item_title_low_color, self._item_title_high_color
        )
        # processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

        processed = cv2.threshold(
            processed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]
        cv2.imshow("test2", cv2.resize(processed, None, fx=10, fy=10))
        cv2.waitKey(1)
        contours, _ = cv2.findContours(
            processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        end = time.time()
        print("Time for processing:", end - start)

        res = self.read_from_img(
            processed,
            f"--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
        )
        print("Time for reading", time.time() - end)
        return res
