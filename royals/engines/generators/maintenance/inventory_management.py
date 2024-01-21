import logging
from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, controller
from botting.utilities import config_reader, take_screenshot
from ..interval_based import TriggerBasedGenerator
from royals.game_data import MaintenanceData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class InventoryManager(TriggerBasedGenerator):

    generator_type = "Maintenance"

    def __init__(self, data: MaintenanceData, tab_to_watch: str = 'Equip', interval: int = 600) -> None:
        super().__init__(data, interval)
        self.tab_to_watch = tab_to_watch

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._space_left = 96

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @property
    def data_requirements(self) -> tuple:
        return "inventory_menu",

    def _setup(self) -> QueueAction | None:
        client_img = take_screenshot(self.data.handle)
        if not self.data.inventory_menu.is_displayed(self.data.handle, client_img):
            self._set_status("Idle")
            return QueueAction(
                identifier="Opening inventory",
                priority=1,
                action=partial(
                    controller.press, self.data.handle, self._key, silenced=True
                ),
                update_generators={f"{repr(self)}_status": "Setup"}
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
                update_generators={f"{repr(self)}_status": "Setup"}
            )
        else:
            curr_tab = self.data.inventory_menu.get_active_tab(self.data.handle, client_img)
            if curr_tab is None:
                self._fail_count += 1
                return
            nbr_press = self.data.inventory_menu.get_tab_count(curr_tab, self.tab_to_watch)
            if nbr_press > 0:
                self._set_status("Idle")
                return QueueAction(
                    identifier=f"Tabbing {nbr_press} from {curr_tab} to {self.tab_to_watch}",
                    priority=1,
                    action=partial(self._press_n_times, self.data.handle, 'tab', nbr_press),
                    update_generators={f"{repr(self)}_status": "Setup"}
                )
            self._set_status("Ready")

    def _update_attributes(self) -> None:
        # Once we are on the relevant tab, update the space left
        self._space_left = self.data.inventory_menu.get_space_left(self.data.handle)
        logger.info(f"Inventory space left: {self._space_left}")

    def _trigger(self) -> QueueAction:
        msg = None
        if self._space_left < 10:
            msg = [f"{self._space_left} slots left in inventory. Please NPC."]
        return QueueAction(
            identifier="Closing Inventory",
            priority=1,
            action=partial(controller.press, self.data.handle, self._key, silenced=True),
            update_generators={f"{repr(self)}_status": "Done"},
            user_message=msg
        )

    def _cleanup_action(self) -> partial:
        return partial(controller.press, self.data.handle, self._key, silenced=True)

    def _confirm_cleaned_up(self) -> bool:
        return not self.data.inventory_menu.is_displayed(self.data.handle)

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
