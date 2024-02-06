import logging
import time
from functools import partial

from botting import PARENT_LOG
from botting.core import QueueAction, DecisionGenerator
from botting.utilities import config_reader, take_screenshot
from royals.engines.generators.interval_based import IntervalBasedGenerator
from royals.engines.generators.step_based import StepBasedGenerator
from royals.game_data import MaintenanceData
from royals.models_implementations.mechanics import MinimapConnection
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
        space_left_alert: int = 100,
        procedure: int = PROC_REQUEST_MYSTIC_DOOR,
        nodes_for_door: list[tuple] = None,
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
        if self.procedure == self.PROC_USE_MYSTIC_DOOR:
            self.data.update(allow_teleport=True)

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._minimap_key = eval(
            config_reader("keybindings", self.data.ign, "Non Skill Keys")
        )["Minimap Toggle"]
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

        self._original_minimap = self.data.current_minimap  # For failsafe purposes

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
                self._move_to_shop,
                # self._move_to_shop_portal,
                # self._cleanup_inventory,
            ]

        return common + procedure_specific_steps

    @property
    def initial_data_requirements(self) -> tuple:
        return "inventory_menu", "current_minimap_area_box", "minimap_grid"

    def _update_continuous_data(self) -> None:
        if self.current_step > 0:
            self.data.update("current_minimap_position")

    def _failsafe(self) -> QueueAction | None:
        if not self._failsafe_enabled:
            return

        if self.current_step > self.num_steps:
            if self.data.inventory_menu.is_displayed(
                self.data.handle, self.data.current_client_img
            ):
                return InventoryActions.toggle(self.generator, self._key)
            self.current_step = 0
            self._next_call = time.perf_counter() + self.interval
            print("Done!")
            self._failsafe_enabled = True
            raise self.skip_iteration

        elif self.steps[max(1, self.current_step) - 1] == self._use_mystic_door:
            # TODO - Add failsafe that confirms mystic door is indeed active.
            pass

        elif self.steps[max(1, self.current_step) - 1] == self._enter_door:
            # Confirm if character is indeed in town.
            time.sleep(1.5)
            if (
                not self.data.current_minimap.get_minimap_state(self.data.handle)
                == "Partial"
            ):
                return InventoryActions.toggle(
                    self.generator, self._minimap_key, ("current_minimap_area_box",)
                )
            box = self.data.current_minimap.get_map_area_box(self.data.handle)
            if (box.width, box.height) == (
                self._original_minimap.map_area_width,
                self._original_minimap.map_area_height,
            ):
                self.current_step -= 1
                return
            elif (box.width, box.height) == (
                self.data.current_map.path_to_shop.minimap.map_area_width,
                self.data.current_map.path_to_shop.minimap.map_area_height,
            ):
                self.data.update(current_map=self.data.current_map.path_to_shop)
                self.data.update(current_minimap=self.data.current_map.minimap)
                self.data.update(current_client_img=take_screenshot(self.data.handle))
                door_node = self._original_minimap.grid.node(
                    *getattr(self, "door_target")
                )
                if MinimapConnection.PORTAL in door_node.connections_types:
                    idx = door_node.connections_types.index(MinimapConnection.PORTAL)
                    door_node.connections.pop(idx)
                    door_node.connections_types.pop(idx)
                    print("popped")
                setattr(self, "door_target", None)
                self._failsafe_enabled = False
            else:
                breakpoint()

    def _exception_handler(self, e: Exception) -> None:
        raise e
