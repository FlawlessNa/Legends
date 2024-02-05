import logging
import time
from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionGenerator
from botting.utilities import config_reader
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.engines.generators.step_based import StepBasedGenerator
from royals.game_data import MaintenanceData
from royals.models_implementations.mechanics.inventory import (
    InventoryChecks,
    InventoryActions,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class InventoryManager(IntervalBasedGenerator, StepBasedGenerator, InventoryChecks):
    """
    Interval-based AND Step-based generator that checks the inventory space left.
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

    def __init__(
        self,
        data: MaintenanceData,
        tab_to_watch: str = "Equip",
        interval: int = 180,
        deviation: float = 0.0,
        space_left_alert: int = 10,
        procedure: int = PROC_REQUEST_MYSTIC_DOOR,
        nodes_for_door: list[tuple] = None
    ) -> None:
        """
        :param data: Engine data object
        :param tab_to_watch: The inventory tab to watch for space left. # TODO - check multiple?
        :param interval: Interval at which this generator is triggered
        :param deviation: Random deviation to be added to the interval
        :param space_left_alert: Number of slots left to trigger the procedure
        :param procedure: Procedure to be executed if space left is below the threshold
        :param nodes_for_door: If procedure involves mystic door and this parameter is
            not None, the generator will use one node at random to get to the door spot.
            Otherwise, the door spot will be extracted from current minimap,
            if specified. If not, the current character's position is used.
            (Note: This may cause issue if too close to a ladder or another portal. This
            is because once the entire procedure is completed, the character may
            inadvertently go back into the door solely due to regular Rotation)
        """
        super().__init__(data, interval, deviation)
        self.tab_to_watch = tab_to_watch
        self.space_left_alert = space_left_alert
        self.procedure = procedure

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        super(DecisionGenerator, self).__init__(self, data, self._key)
        self._space_left = 96

        if self.procedure == self.PROC_USE_MYSTIC_DOOR:
            self._door_key = eval(
                config_reader("keybindings", self.data.ign, "Skill Keys")
            )["Mystic Door"]
        else:
            self._door_key = None
        self.nodes_for_door = nodes_for_door
        self.door_target = None

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @property
    def steps(self) -> list[callable]:
        common = [partial(self._get_space_left, self.tab_to_watch)]
        procedure_specific_steps = []

        if self.procedure == self.PROC_DISCORD_ALERT:
            procedure_specific_steps = [self._trigger_discord_alert]

        elif self.procedure == self.PROC_USE_TOWN_SCROLL:
            raise NotImplementedError

        elif self.procedure == self.PROC_USE_MYSTIC_DOOR:
            procedure_specific_steps = [
                partial(self._get_to_door_spot, self.nodes_for_door),
                self._use_mystic_door,
                self._enter_door,
                self._ensure_in_town,
                self._move_to_shop_portal,
                self._cleanup_inventory,
            ]

        return common + procedure_specific_steps

    @property
    def initial_data_requirements(self) -> tuple:
        return ("inventory_menu",)

    def _update_continuous_data(self) -> None:
        if self.current_step > 0:
            self.data.update('current_minimap_position')

    def _step_based_failsafe(self) -> QueueAction | None:
        if self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        ):
            return InventoryActions.toggle(self.generator, self._key)
        self.current_step = 0
        self._next_call = time.perf_counter() + self.interval
        raise self.skip_iteration

    def _exception_handler(self, e: Exception) -> None:
        raise e
