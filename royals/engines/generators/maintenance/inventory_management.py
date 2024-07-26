import logging
import time
from functools import partial, cached_property

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
        space_left_alert: int = 10,
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
            self._teleport = self.data.character.skills["Teleport"]
            self.data.update(allow_teleport=True)

        self._key = eval(config_reader("keybindings", self.data.ign, "Non Skill Keys"))[
            "Inventory Menu"
        ]
        self._minimap_key = eval(
            config_reader("keybindings", self.data.ign, "Non Skill Keys")
        )["Minimap Toggle"]
        self._npc_chat_key = eval(
            config_reader("keybindings", self.data.ign, "Non Skill Keys")
        )["NPC Chat"]
        super(DecisionGenerator, self).__init__(
            self, data, self._key, self._npc_chat_key
        )
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
        self._original_map = self.data.current_map  # For failsafe purposes

    def __repr__(self) -> str:
        return f"InventoryManager({self.tab_to_watch})"

    @cached_property
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
                self._open_npc_shop,
                partial(self._activate_tab, self.tab_to_watch),
                self._cleanup_inventory,
                self._close_npc_shop,
                self._return_to_door,
            ]
        elif self.procedure == self.PROC_REQUEST_MYSTIC_DOOR:
            raise NotImplementedError

        return common + procedure_specific_steps

    @property
    def initial_data_requirements(self) -> tuple:
        return "inventory_menu", "current_minimap_area_box", "minimap_grid"

    def _update_continuous_data(self) -> None:
        if self.current_step > 0:
            self.data.update("current_minimap_position")

        if hasattr(self, "_slots_cleaned"):
            self._space_left += self._slots_cleaned
            delattr(self, "_slots_cleaned")

    def _failsafe(self) -> QueueAction | None:
        started_at = getattr(self, 'cleanup_procedure_started_at', time.perf_counter())
        if time.perf_counter() - started_at > 180:
            raise ValueError(f"{self} has been running for too long.")

        if not self._failsafe_enabled:
            return

        if self.current_step > self.num_steps:
            return self._cleanup_completed()

        elif self.steps[max(1, self.current_step) - 1] == self._use_mystic_door:
            return self._confirm_door()

        elif self.steps[max(1, self.current_step) - 1] == self._enter_door:
            return self._confirm_in_town()

        elif self.steps[max(1, self.current_step) - 1] == self._return_to_door:
            return self._confirm_in_original_map()

    def _exception_handler(self, e: Exception) -> None:
        if self.steps[self.current_step] == self._enter_door:
            logger.info(f"{self} has failed to enter the door. Retrying.")
            self.current_step -= 2
            self._current_step_executed = 0
            self.blocked = False
            return
        raise e

    def _cleanup_completed(self) -> QueueAction | None:
        if self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        ):
            return InventoryActions.toggle(self.generator, self._key)
        self.current_step = 0
        self._next_call = time.perf_counter() + self.interval
        self._failsafe_enabled = True
        self.door_target = None
        if hasattr(self, "return_door_target"):
            delattr(self, "return_door_target")
        if hasattr(self, "npcs_positions"):
            delattr(self, "npcs_positions")
        if hasattr(self, "_direction"):
            delattr(self, "_direction")
        if hasattr(self, 'cleanup_procedure_started_at'):
            delattr(self, 'cleanup_procedure_started_at')
        logger.info(f"{self} has completed the inventory cleanup procedure.")
        self.generator.unblock_generators("All", id(self.generator))
        raise self.skip_iteration

    def _confirm_door(self) -> QueueAction | None:
        # TODO - Add failsafe that confirms mystic door is indeed active.
        pass

    def _confirm_in_town(self) -> QueueAction | None:
        """
        Start by ensuring minimap is partially opened.
        Then look at its dimensions and see if it matches the town's minimap.
        :return:
        """
        if (
            not self.data.current_minimap.get_minimap_state(self.data.handle)
            == "Partial"
        ):
            return InventoryActions.toggle(
                self.generator, self._minimap_key, ("current_minimap_area_box",)
            )

        # Check dimensions
        box = self.data.current_minimap.get_map_area_box(self.data.handle)
        if (box.width, box.height) == (
            self._original_minimap.map_area_width,
            self._original_minimap.map_area_height,
        ):
            self.current_step -= 1  # Go back to the previous step
            return

        elif (box.width, box.height) == (
            self.data.current_map.path_to_shop.minimap.map_area_width,
            self.data.current_map.path_to_shop.minimap.map_area_height,
        ):
            # We are in the town, update data appropriately and proceed to next step
            self.data.update(current_map=self.data.current_map.path_to_shop)
            self.data.update(current_minimap=self.data.current_map.minimap)
            self.data.update(current_client_img=take_screenshot(self.data.handle))

            # Remove the PORTAL connection from the door in original grid
            door_node = self._original_minimap.grid.node(*getattr(self, "door_target"))
            if MinimapConnection.PORTAL in door_node.connections_types:
                idx = door_node.connections_types.index(MinimapConnection.PORTAL)
                door_node.connections.pop(idx)
                door_node.connections_types.pop(idx)

            setattr(self, "door_target", None)
            self._failsafe_enabled = False  # No more failsafe-ing until next step
        else:
            breakpoint()

    def _confirm_in_original_map(self) -> QueueAction | None:
        # Check dimensions
        time.sleep(2)
        box = self.data.current_minimap.get_map_area_box(self.data.handle)
        if (box.width, box.height) == (
            self.data.current_minimap.map_area_width,
            self.data.current_minimap.map_area_height,
        ):
            self.current_step -= 1  # Go back to the previous step
            return

        elif (box.width, box.height) == (
            self._original_minimap.map_area_width,
            self._original_minimap.map_area_height,
        ):
            # We are back in original, update data and proceed
            self.data.update(current_map=self._original_map)
            self.data.update(current_minimap=self._original_minimap)
            self.data.update(current_client_img=take_screenshot(self.data.handle))
            self.data.update("current_minimap_area_box", "minimap_grid")
            self.data.update(
                current_minimap_position=self.data.current_minimap.get_character_positions(
                    self.data.handle,
                    client_img=self.data.current_client_img,
                    map_area_box=self.data.current_minimap_area_box,
                ).pop()
            )
