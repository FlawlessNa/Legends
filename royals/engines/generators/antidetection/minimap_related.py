import logging
import math
import numpy as np
import random
from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, controller
from botting.utilities import config_reader, take_screenshot
from royals.actions import write_in_chat
from royals.game_data import AntiDetectionData
from ..trigger_based import TriggerBasedGenerator


logger = logging.getLogger(PARENT_LOG + "." + __name__)


class CheckStillInMap(TriggerBasedGenerator):

    generator_type = "AntiDetection"

    def __init__(self,
                 data: AntiDetectionData,
                 interval: int = 10
                 ):
        super().__init__(data, interval)
        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Minimap Toggle"
        ]
        self._current_title_img = self._prev_title_img = None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}"

    @property
    def data_requirements(self) -> tuple:
        return tuple()

    def _setup(self) -> QueueAction | None:
        if not self.data.current_minimap.get_minimap_state(self.data.handle) == "Full":
            self._set_status("Idle")
            return QueueAction(
                identifier="Opening minimap to Fully Displayed",
                priority=1,
                action=partial(
                    controller.press, self.data.handle, self._key, silenced=True
                ),
                update_game_data={f"{repr(self)}_status": "Setup"}
            )
        else:
            mouse_pos = controller.get_mouse_pos(self.data.handle)
            center = self.data.current_minimap.get_minimap_title_box(self.data.handle).center
            if mouse_pos is None or abs(math.dist(mouse_pos, center)) < 200:
                self._set_status("Idle")
                target = center[0] + random.randint(300, 600), center[1] + random.randint(300, 600)
                return QueueAction(
                    identifier="Moving Mouse away from Minimap",
                    priority=1,
                    action=partial(
                        controller.mouse_move, self.data.handle, target
                    ),
                    update_game_data={f"{repr(self)}_status": "Setup"}
                )

        self._set_status("Ready")

    def _update_attributes(self) -> None:
        if self._current_title_img is None:
            self._current_title_img = take_screenshot(self.data.handle, self.data.current_minimap.get_minimap_title_box(self.data.handle))
            self._prev_title_img = self._current_title_img.copy()
        else:
            self._prev_title_img = self._current_title_img.copy()
            self._current_title_img = take_screenshot(self.data.handle, self.data.current_minimap.get_minimap_title_box(self.data.handle))

    def _trigger(self) -> QueueAction | None:
        if not np.array_equal(self._current_title_img, self._prev_title_img):

            self._set_status("Idle")
            return self._reaction()
        else:
            self._set_status("Done")

    def _confirm_cleaned_up(self) -> bool:
        return True

    def _cleanup_action(self) -> partial:
        pass

    def _reaction(self) -> QueueAction:
        """
        Triggers emergency reaction, which is three-fold:
        1. Block bot from continuing until user calls RESUME from discord.
            Note: If no RESUME within 60 seconds, the bot stops.
        2. Random reaction in general chat
        3. Send Discord Alert
        :return:
        """
        reaction_text = random.choice(
            [
                "wtf",
                "wut",
                "wtf?",
                "hmmm?",
                "?",
                "???",
                "uh",
                "huh",
                "tha hell",
                "wth",
                "wth?",
                "wtf!",
                "wtf!?",
            ]
        )
        logger.warning(
            f"Character not in expected map!."
        )

        func = partial(
            write_in_chat,
            handle=self.data.handle,
            message=reaction_text,
            channel="general",
        )
        self.data.block("Rotation")
        return QueueAction(
            f"{self.__class__.__name__} reaction",
            priority=1,
            action=func,
            user_message=[
                f"""
                Character is not in the proper map!
                """,
                self._current_title_img,
            ],
            update_game_data={f"{repr(self)}_status": "Done"}
        )
