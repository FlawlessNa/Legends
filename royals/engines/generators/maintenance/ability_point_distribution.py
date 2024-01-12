import asyncio
import time
from functools import partial

from botting.core import DecisionGenerator, QueueAction, controller
from botting.utilities import config_reader
from royals import RoyalsData


class DistributeAP(DecisionGenerator):
    def __init__(self, game_data: RoyalsData) -> None:
        self.data = game_data

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            'Ability Menu'
        ]
        self._offset_box = self.data.ability_menu.stat_mapper[self.data.character.main_stat]

    def _failsafe(self):
        pass

    def __call__(self):
        self.data.update("current_level")
        self._current_lvl = self.data.current_level
        return iter(self)

    def __next__(self):
        self.data.update("current_level")
        if self.data.current_level > self._current_lvl:

            if not self.data.ability_menu.is_displayed(self.data.handle):
                return QueueAction(
                    identifier="Opening ability menu",
                    priority=1,
                    action=partial(controller.press,
                                   self.data.handle,
                                   self._key,
                                   silenced=True
                                   ),
                )
            else:
                # Start by looking whether we have AP to distribute
                ap_available = self.data.ability_menu.get_available_ap(self.data.handle)
                if ap_available > 0:
                    # If we do, distribute it
                    return QueueAction(
                        identifier="Distributing AP",
                        priority=1,
                        action=partial(self._distribute_ap,
                                       self.data.handle,
                                       ...,
                                       ap_available),
                    )
                else:
                    self._current_lvl = self.data.current_level
                    return QueueAction(
                        identifier="Closing ability menu",
                        priority=1,
                        action=partial(controller.press,
                                       self.data.handle,
                                       self._key,
                                       silenced=True
                                       )
                    )
        else:
            time.sleep(60)

    @staticmethod
    async def _distribute_ap(handle: int,
                             target_stat: tuple[int, int],
                             nbr_of_clicks: int = 5):
        await controller.mouse_move(handle, target)
        for _ in range(nbr_of_clicks):
            await controller.click()
            await asyncio.sleep(0.1)