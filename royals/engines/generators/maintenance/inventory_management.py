import time
from functools import partial

from botting.core import DecisionGenerator, QueueAction, controller
from botting.utilities import config_reader, take_screenshot
from royals.game_data import MaintenanceData


class InventoryManager(DecisionGenerator):

    generator_type = "Maintenance"

    def __init__(self, data: MaintenanceData, tab_to_watch: str = 'Equip') -> None:
        super().__init__(data)
        self.tab_to_watch = tab_to_watch

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._next_call = time.perf_counter()
        self._space_left = 96

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @property
    def data_requirements(self) -> tuple:
        return "inventory_menu",

    def _failsafe(self):
        pass

    def _next(self):
        if time.perf_counter() < self._next_call:
            return

        # Block AP distribution until the entire procedure is done
        setattr(self.data, "DistributeAP", True)

        # Start by opening up menu
        client_img = take_screenshot(self.data.handle)
        if not self.data.inventory_menu.is_displayed(self.data.handle, client_img):
            self._next_call = time.perf_counter() + 1
            return QueueAction(
                identifier="Opening inventory",
                priority=1,
                action=partial(
                    controller.press, self.data.handle, self._key, silenced=True, cooldown=0
                ),
            )

        # Once menu is open, make sure it is extended
        if not self.data.inventory_menu.is_extended(self.data.handle, client_img):
            self._next_call = time.perf_counter() + 2
            box = self.data.inventory_menu.get_abs_box(self.data.handle, self.data.inventory_menu.extend_button)
            target = box.random()
            return QueueAction(
                identifier="Extending inventory",
                priority=1,
                action=partial(self._expand_inv, self.data.handle, target),
            )

        # Once it is extended, Get to the relevant tab
        curr_tab = self.data.inventory_menu.get_active_tab(self.data.handle, client_img)
        nbr_press = self.data.inventory_menu.get_tab_count(curr_tab, self.tab_to_watch)
        if nbr_press > 0:
            self._next_call = time.perf_counter() + 2
            return QueueAction(
                identifier=f"Tabbing {nbr_press} times from {curr_tab} to {self.tab_to_watch}",
                priority=1,
                action=partial(self._press_n_times, self.data.handle, 'tab', nbr_press)
            )

        # Once we are on the relevant tab, update the space left
        self._space_left = self.data.inventory_menu.get_space_left(self.data.handle, client_img)

        # Unblock AP distribution
        setattr(self.data, "DistributeAP", False)

        # TODO - Create methodology for automated NPCing
        # Temporarily, we merely send a discord message
        if self._space_left < 10:
            self._next_call = time.perf_counter() + 600
            return QueueAction(
                identifier="Inventory Full",
                priority=1,
                action=partial(controller.press, self.data.handle, self._key, silenced=True, cooldown=0),
                user_message=[f"{self._space_left} slots left in inventory. Please NPC."]
            )
        else:
            self._next_call = time.perf_counter() + 600
            return QueueAction(
                identifier="Closing Inventory",
                priority=1,
                action=partial(controller.press, self.data.handle, self._key, silenced=True, cooldown=0),
            )

    @staticmethod
    async def _expand_inv(
        handle: int, target: tuple[int, int]
    ):
        await controller.mouse_move(handle, target)
        await controller.click(handle)

    @staticmethod
    async def _press_n_times(handle: int, key: str, nbr_of_presses: int = 1):
        for _ in range(nbr_of_presses):
            await controller.press(handle, key, silenced=True)