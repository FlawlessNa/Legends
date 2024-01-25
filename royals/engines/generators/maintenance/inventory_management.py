import logging
import time
from functools import partial

from botting import PARENT_LOG
from botting.core import GeneratorUpdate, QueueAction, controller
from botting.utilities import config_reader
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.game_data import MaintenanceData

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class InventoryManager(IntervalBasedGenerator):
    """
    Interval-based generator that regularly checks the inventory space left.
    If the space left is below a certain threshold, it will call the cleanup procedure.
    There are 4 procedures available:
    - Discord Alert to the user
    - Use Nearest Town and clear inventory, then come back (Not implemented)
    - Use Mystic Door and clear inventory, then come back
    - Request another Executor to use Mystic Door, get to that door and clear inventory,
        then come back (Not yet Implemented)
    """

    generator_type = "Maintenance"
    PROC_DISCORD_ALERT = 1
    PROC_USE_TOWN_SCROLL = 2
    PROC_USE_MYSTIC_DOOR = 3
    PROC_REQUEST_MYSTIC_DOOR = 4

    def __init__(self,
                 data: MaintenanceData,
                 tab_to_watch: str = 'Equip',
                 interval: int = 600,
                 deviation: float = 0.0,
                 space_left_alert: int = 10,
                 procedure: int = PROC_USE_MYSTIC_DOOR
                 ) -> None:
        super().__init__(data, interval, deviation)
        self.tab_to_watch = tab_to_watch
        self.space_left_alert = space_left_alert
        self.procedure = procedure

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._space_left = 96
        self._fail_count = 0
        self._is_displayed = self._is_extended = False
        self._current_tab = None

        if self.procedure == self.PROC_USE_MYSTIC_DOOR:
            self._door_key = eval(config_reader("keybindings", self.data.ign, "Skill Keys"))[
                'Mystic Door'
            ]
        else:
            self._door_key = None

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @property
    def initial_data_requirements(self) -> tuple:
        return "inventory_menu",

    def _update_continuous_data(self) -> None:
        self._is_displayed = self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        )
        if self._is_displayed:
            self._is_extended = self.data.inventory_menu.is_extended(
                self.data.handle, self.data.current_client_img
            )
        if self._is_extended:
            self._current_tab = self.data.inventory_menu.get_active_tab(
                self.data.handle, self.data.current_client_img
            )
        if self._current_tab == self.tab_to_watch:
            self._space_left = self.data.inventory_menu.get_space_left(
                self.data.handle, self.data.current_client_img
            )
            logger.info(f"Inventory space left: {self._space_left}")

    def _failsafe(self) -> QueueAction | None:
        """
        TODO - If Using Mystic Door, check chat to see if out of Magic Rocks,
        in which case trigger error + discord alert
        :return:
        """
        pass

    def _exception_handler(self, e: Exception) -> None:
        raise e

    def _next(self) -> QueueAction | None:
        if not self._is_displayed:
            return self._toggle_inventory_menu()
        elif not self._is_extended:
            return self._expand_inventory_menu()
        elif self._current_tab is None:
            self._fail_count += 1
            return
        elif self._current_tab != self.tab_to_watch:
            return self._toggle_tab()
        elif self._space_left <= self.space_left_alert:
            return self._cleanup_handler()

        else:
            self._next_call = time.perf_counter() + self.interval

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

    def _toggle_inventory_menu(self) -> QueueAction:
        self.blocked = True
        return QueueAction(
            identifier="Toggling inventory menu",
            priority=1,
            action=partial(
                controller.press, self.data.handle, self._key, silenced=True
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={"blocked": False},
            )
        )

    def _expand_inventory_menu(self) -> QueueAction:
        box = self.data.inventory_menu.get_abs_box(
            self.data.handle, self.data.inventory_menu.extend_button
        )
        target = box.random()
        return QueueAction(
            identifier="Extending inventory",
            priority=1,
            action=partial(
                self._expand_inv,
                self.data.handle,
                target,
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(self),
                generator_kwargs={"blocked": False},
            )
        )

    def _toggle_tab(self) -> QueueAction | None:

        nbr_press = self.data.inventory_menu.get_tab_count(
            self._current_tab, self.tab_to_watch
        )
        if nbr_press > 0:
            self.blocked = True
            return QueueAction(
                identifier=f"Tabbing {nbr_press} from {self._current_tab} to {self.tab_to_watch}",
                priority=1,
                action=partial(self._press_n_times, self.data.handle, 'tab', nbr_press),
                update_generators=GeneratorUpdate(
                    generator_id=id(self),
                    generator_kwargs={"blocked": False},
                )
            )

    def _cleanup_handler(self) -> QueueAction | None:
        if self.procedure == self.PROC_DISCORD_ALERT:
            return QueueAction(
                identifier="Inventory Full - Discord Alert",
                priority=1,
                user_message=[f"{self._space_left} slots left in inventory."]
            )
        elif self.procedure == self.PROC_USE_MYSTIC_DOOR:
            pass

        elif self.procedure in [
            self.PROC_USE_TOWN_SCROLL, self.PROC_REQUEST_MYSTIC_DOOR
        ]:
            raise NotImplementedError
