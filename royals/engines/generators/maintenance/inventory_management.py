import logging
import time
from functools import partial

from botting import PARENT_LOG
from botting.core import DecisionGenerator, QueueAction, controller
from botting.utilities import config_reader, take_screenshot
from royals.game_data import MaintenanceData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class InventoryManager(DecisionGenerator):

    generator_type = "Maintenance"

    def __init__(self, data: MaintenanceData, tab_to_watch: str = 'Equip', interval: int = 600) -> None:
        super().__init__(data)
        self.tab_to_watch = tab_to_watch
        self.interval = interval

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._next_call = time.perf_counter()
        self._space_left = 96
        self._fail_count = 0

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @property
    def data_requirements(self) -> tuple:
        return "inventory_menu",

    def _failsafe(self):
        if self._fail_count > 10:
            logger.critical("Inventory Manager has failed too many times. Stopping.")
            return QueueAction(
                identifier="Inventory Manager Failsafe",
                priority=1,
                action=partial(lambda: RuntimeError, "Inventory Manager Failsafe"),
                user_message=["Inventory Manager has failed too many times. Stopping."]
            )

    def _next(self):
        status = self._get_status()

        if status == "Idle":
            return

        elif status == "Ready":
            client_img = take_screenshot(self.data.handle)
            if not self.data.inventory_menu.is_displayed(self.data.handle, client_img):
                self._set_status("Idle")
                return QueueAction(
                    identifier="Opening inventory",
                    priority=1,
                    action=partial(
                        controller.press, self.data.handle, self._key, silenced=True
                    ),
                    update_game_data={f"{repr(self)}_status": "Ready"}
                )
            elif not self.data.inventory_menu.is_extended(self.data.handle, client_img):
                self._set_status("Idle")
                box = self.data.inventory_menu.get_abs_box(self.data.handle, self.data.inventory_menu.extend_button)
                target = box.random()
                return QueueAction(
                    identifier="Extending inventory",
                    priority=1,
                    action=partial(
                        self._expand_inv,
                        self.data.handle,
                        target,
                    ),
                    update_game_data={f"{repr(self)}_status": "Ready"}
                )
            else:
                curr_tab = self.data.inventory_menu.get_active_tab(self.data.handle, client_img)
                if curr_tab is None:
                    self._fail_count += 1
                    return
                else:
                    nbr_press = self.data.inventory_menu.get_tab_count(curr_tab, self.tab_to_watch)
                    if nbr_press > 0:
                        self._set_status("Idle")
                        return QueueAction(
                            identifier=f"Tabbing {nbr_press} from {curr_tab} to {self.tab_to_watch}",
                            priority=1,
                            action=partial(self._press_n_times, self.data.handle, 'tab', nbr_press),
                            update_game_data={f"{repr(self)}_status": "Ready"}
                        )

                    # Once we are on the relevant tab, update the space left
                    self._space_left = self.data.inventory_menu.get_space_left(self.data.handle, client_img)
                    logger.info(f"Inventory space left: {self._space_left}")
                    self._set_status("Idle")
                    setattr(self.data, "DistributeAP", False)
                    return self._inventory_handler()

        elif status == "Done":
            if self.data.inventory_menu.is_displayed(self.data.handle):
                self._set_status("Idle")
                return QueueAction(
                    identifier="Closing inventory",
                    priority=1,
                    action=partial(
                        controller.press, self.data.handle, self._key, silenced=True
                    ),
                    update_game_data={f"{repr(self)}_status": "Done"}
                )
            else:
                self._next_call = time.perf_counter() + self.interval

    def _get_status(self):
        if time.perf_counter() < self._next_call:
            return "Idle"
        else:
            return getattr(self.data, f"{repr(self)}_status")

    def _set_status(self, status: str):
        setattr(self.data, f"{repr(self)}_status", status)

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

    def _inventory_handler(self) -> QueueAction:
        msg = None
        if self._space_left < 10:
            msg = [f"{self._space_left} slots left in inventory. Please NPC."]
        return QueueAction(
            identifier="Closing Inventory",
            priority=1,
            action=partial(controller.press, self.data.handle, self._key, silenced=True),
            update_game_data={f"{repr(self)}_status": "Done"},
            user_message=msg
        )