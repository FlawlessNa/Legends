import logging
import math
import numpy as np
import time
import random
from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, controller, DecisionGenerator, GeneratorUpdate
from botting.utilities import config_reader
from royals.game_data import AntiDetectionData
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.engines.generators.antidetection.reactions import AntiDetectionReactions


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class CheckStillInMap(IntervalBasedGenerator, AntiDetectionReactions):
    generator_type = "AntiDetection"

    @property
    def reaction_choices(self) -> list:
        return [
            "wtf",
            "wassup?",
            "why?",
            "why" "?",
            "???",
            "tha hell",
            "wth",
            "wth?",
            "wtf!",
            "wtf!?",
        ]

    def __init__(
        self,
        data: AntiDetectionData,
        interval: int = 5,
        cooldown: int = 5,
        max_reactions: int = 2,
    ):
        super().__init__(data, interval, deviation=0)
        super(DecisionGenerator, self).__init__(cooldown, max_reactions)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Minimap Toggle"
        ]
        self._current_title_img = self._prev_title_img = None
        self._fail_counter = 0

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    @property
    def initial_data_requirements(self) -> tuple:
        return tuple()

    def _update_continuous_data(self) -> None:
        self.data.update(
            "current_minimap_state",
            "current_entire_minimap_box",
            "current_minimap_area_box",
            "current_minimap_title_box",
        )
        if self._current_title_img is None:
            self._current_title_img = (
                self.data.current_minimap_title_box.extract_client_img(
                    self.data.current_client_img
                )
            )
            self._prev_title_img = self._current_title_img.copy()
        else:
            self._prev_title_img = self._current_title_img.copy()
            self._current_title_img = (
                self.data.current_minimap_title_box.extract_client_img(
                    self.data.current_client_img
                )
            )

    def _failsafe(self) -> QueueAction | None:
        if self._reaction_counter >= self.max_reactions:
            self._reaction_counter = 0
            self.blocked = True
            return

        res = self._ensure_fully_displayed()
        if res:
            return res

        elif self._fail_counter > 0:
            # Make sure cursor is not on minimap
            mouse_pos = controller.get_mouse_pos(self.data.handle)
            center = self.data.current_minimap_title_box.center
            if mouse_pos is None or abs(math.dist(mouse_pos, center)) < 200:
                self.blocked = True
                target = (
                    center[0] + random.randint(300, 600),
                    center[1] + random.randint(300, 600),
                )
                return QueueAction(
                    identifier="Moving Mouse away from Minimap",
                    priority=1,
                    action=partial(controller.mouse_move, self.data.handle, target),
                    update_generators=GeneratorUpdate(
                        generator_id=id(self),
                        generator_kwargs={"blocked": False},
                    ),
                )

    def _next(self) -> QueueAction | None:
        if not np.array_equal(self._current_title_img, self._prev_title_img):
            self._fail_counter += 1
            logger.warning(f"{self} Fail Counter at {self._fail_counter}.")
            import cv2
            cv2.imshow("prev", self._prev_title_img)
            cv2.imshow("current", self._current_title_img)  #TODO - Fix mechanics it doesnt work right now!
            cv2.waitKey(1)
            # self._current_title_img = self._prev_title_img.copy()

        else:
            if self._fail_counter > 0:
                logger.info(f"{self} fail counter reset at 0.")
            self._fail_counter = 0
            self._reaction_counter = 0
            self._next_call = time.perf_counter() + self.interval

        if self._fail_counter >= 2:
            self.data.block("Rotation")
            self.data.block("Maintenance")
            msg = f"""
                        Minimap Title Img has changed. Bot is now on hold.
                        Send Resume to continue.
                        """
            reaction = self._reaction(
                self.data.handle, [msg, self.data.current_client_img]
            )
            if reaction is not None:
                logger.warning(
                    f"Rotation Blocked. Sending random reaction to chat due to {self}."
                )
            return reaction

    def _exception_handler(self, e: Exception) -> None:
        if self._error_counter >= 4:
            logger.critical(f"Too many errors in {self}. Exiting.")
            raise e

        return self._ensure_fully_displayed()

    def _ensure_fully_displayed(self) -> QueueAction | None:

        if not self.data.current_minimap_state == "Full":
            self.blocked = True
            return QueueAction(
                identifier="Opening minimap to Fully Displayed",
                priority=1,
                action=partial(
                    controller.press, self.data.handle, self._key, silenced=True
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={"blocked": False},
                ),
            )
