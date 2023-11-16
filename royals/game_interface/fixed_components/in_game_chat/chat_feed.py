import cv2
import numpy as np
import os

from functools import cached_property
from typing import Generator

from .chat_lines import ChatLine
from royals.game_interface import InGameToggleableVisuals
from paths import ROOT
from botting.utilities import Box, take_screenshot, find_image


class ChatFeed(InGameToggleableVisuals):
    """
    Base class for in-game chat feed.
    Contains chat feed coordinates and methods for splitting feed into Chat Lines, as well as method to detect whether the chat feed is displayed.
    Contains method to retrieve the exact chat feed box, which varies in-game based on how many lines are displayed.
    """

    # These class attributes are the same for both large and small clients, therefore the same for all instances of ChatFeed.
    _chat_feed_line_height: int = 13
    _chat_feed_displayed_detection_color = ((119, 85, 51), (119, 85, 51))

    # Color to detect if the cursor is over the detection box, which is a hover button that changes color when hovered.
    _chat_feed_displayed_detection_color_alt = (
        (153, 102, 34),
        (153, 102, 34),
    )
    _chat_feed_height_detection_needle: np.ndarray = cv2.imread(
        os.path.join(
            ROOT,
            "royals/game_interface/detection_images/chat_feed_height_detection_needle.png",
        )
    )

    def __init__(self, handle: int) -> None:
        super().__init__(handle)
        if self._large_client:
            self._chat_typing_area: Box = Box(
                left=83,
                right=613,
                top=731,
                bottom=750,
                config="--psm 7",
            )
            self._chat_feed_box = dict(left=4, right=628, bottom=724)
            self._chat_feed_displayed_detection_box = Box(
                left=6, right=82, top=732, bottom=750
            )
            self._chat_feed_height_detection_box = Box(
                left=629, right=642, top=217, bottom=711
            )
        else:
            raise NotImplementedError("Small client not implemented yet")

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """The chat feed itself should never be read from. Instead, individual chat lines should. This function should therefore never be called."""
        raise NotImplementedError(
            "Chat feed should never be read from directly. Read from chat lines instead."
        )

    def is_displayed(self) -> bool:
        """
        Detects whether the chat feed is displayed or not. Check sequentially to avoid a double operation when the first one is true.
        """
        img = take_screenshot(self.handle, self._chat_feed_displayed_detection_box)
        if self._color_detection(
            img,
            needle_color=self._chat_feed_displayed_detection_color,
            pixel_threshold=20,
        ):
            return True
        elif self._color_detection(
            img,
            needle_color=self._chat_feed_displayed_detection_color_alt,
            pixel_threshold=20,
        ):
            return True
        else:
            return False

    def is_showing_latest(self) -> bool:
        """
        # TODO
        Checks whether lines displayed are the latest available lines.
        Only works when:
        - The chat feed is displayed
        - The chat scroll bar is not obstructed by cursor, and
        - At least 4 lines are displayed
        :return: bool
        """
        if (
            not self.is_displayed()
            or self.get_nbr_lines_displayed is None
            or self.get_nbr_lines_displayed < 4
        ):
            return False
        else:
            raise NotImplementedError

    @cached_property
    def get_nbr_lines_displayed(self) -> int | None:
        """
        Returns the number of lines displayed in the chat feed.
        If the chat feed is not displayed or the detection needle is obstructed, returns None.
        This result is cached, as the number of lines displayed is usually not expected to change.
        To force a new detection, delete the cached property.
        For example: self.__dict__.pop('get_nbr_lines_displayed', None)
        :return:
        """
        if not self.is_displayed():
            return
        else:
            img = take_screenshot(self.handle, self._chat_feed_height_detection_box)
            location = find_image(
                img,
                self._chat_feed_height_detection_needle,
                threshold=0.995,
                add_margins=False,
            )
            assert len(location) <= 1, "Multiple chat feed detection images found"
            if location:
                box = location.pop()
                return int(
                    (self._chat_feed_height_detection_box.height - box.center[-1])
                    // self._chat_feed_line_height
                    + 2
                )

    def get_chat_feed_box(self) -> Box | None:
        """
        Returns the box coordinates of the entire chat feed. The box coordinates vary based on how many lines are displayed.
        :return:
        """
        if not self.is_displayed():
            return
        elif self.get_nbr_lines_displayed is not None:
            return Box(
                **self._chat_feed_box,
                top=int(
                    self._chat_feed_box["bottom"]
                    - self._chat_feed_line_height * self.get_nbr_lines_displayed
                ),
            )

    def get_chat_lines_box(self) -> tuple[Box]:
        """
        Partitions the chat feed into individual lines and returns the
        box coordinates of each line, from bottom to top (in-screen), meaning most recent to least recent.
        :return:
        """
        chat_box = self.get_chat_feed_box()
        return tuple(
            reversed(
                [
                    Box(
                        name=f"chat_line_{i}",
                        config="--psm 7",
                        left=self._chat_feed_box["left"],
                        right=self._chat_feed_box["right"],
                        top=chat_box.top + self._chat_feed_line_height * i,
                        bottom=chat_box.top + self._chat_feed_line_height * (i + 1),
                    )
                    for i in range(self.get_nbr_lines_displayed)
                ]
            )
        )

    def parse(self) -> Generator:
        """
        Parses through the visible chat lines and returns a list of ChatLine objects.
        Starts by taking a screenshot of the entire chat. This prevents bugs that could happen
        if new lines appear while the parsing is in progress, as it ensure the original feed remains static.
        :return:
        """
        chat_img = take_screenshot(self.handle, self.get_chat_feed_box())
        lines = reversed(np.split(chat_img, self.get_nbr_lines_displayed, axis=0))
        return (ChatLine.from_img(self.handle, img) for img in lines)
