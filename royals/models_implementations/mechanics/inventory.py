import logging
import random
import time
from functools import partial
from typing import Union

from botting import PARENT_LOG
from botting.core import DecisionGenerator, GeneratorUpdate, QueueAction, controller
from royals.game_data import MaintenanceData, MinimapData
from royals.models_implementations.mechanics import MinimapConnection
from royals.models_implementations.mechanics.path_into_movements import get_to_target

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class InventoryChecks:
    """
    Utility class for InventoryManager.
    Defines all methods used for inventory management.
    """

    def __init__(
        self,
        generator: DecisionGenerator,
        data: Union[MaintenanceData, MinimapData],
        toggle_key: str,
    ) -> None:
        self.generator: DecisionGenerator = generator
        self.data: Union[MaintenanceData, MinimapData] = data
        self._key = toggle_key

    def _ensure_is_displayed(self) -> QueueAction | None:
        if not self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        ):
            return InventoryActions.toggle(self.generator, self._key)

    def _ensure_is_extended(self) -> QueueAction | None:
        if self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        ):
            if not self.data.inventory_menu.is_extended(
                self.data.handle, self.data.current_client_img
            ):
                return InventoryActions.expand_inventory_menu(self.generator)
        else:
            return self._ensure_is_displayed()

    def _ensure_proper_tab(self, tab_to_watch: str) -> QueueAction | None:
        if self.data.inventory_menu.is_extended(
            self.data.handle, self.data.current_client_img
        ):
            attempt = 0
            while attempt < 5:
                active_tab = self.data.inventory_menu.get_active_tab(
                    self.data.handle, self.data.current_client_img
                )
                if active_tab is None:
                    attempt += 1
                    time.sleep(0.5)
                    if attempt == 10:
                        logger.warning(
                            f"Failed to find active tab after {attempt} attempts"
                        )
                        raise ValueError("Failed to find active tab")
                    continue

                elif active_tab != tab_to_watch:
                    nbr_presses = self.data.inventory_menu.get_tab_count(
                        active_tab, tab_to_watch
                    )
                    return InventoryActions.switch_tab(self.generator, nbr_presses)

        else:
            return self._ensure_is_extended()

    def _get_space_left(self, tab_to_watch: str) -> QueueAction | None:
        """
        Counts the number of space left in the Inventory.
        Triggers next steps if inventory left is smaller than threshold, otherwise
        resets until next interval.
        :param tab_to_watch:
        :return:
        """
        active_tab = self.data.inventory_menu.get_active_tab(
            self.data.handle, self.data.current_client_img
        )
        if active_tab == tab_to_watch:
            space_left = self.data.inventory_menu.get_space_left(
                self.data.handle, self.data.current_client_img
            )
            logger.info(f"Inventory space left: {space_left}")
            setattr(self, "_space_left", space_left)

        else:
            return self._ensure_proper_tab(tab_to_watch)

    def _get_to_door_spot(
        self, nodes: list[tuple[int, int]] | None
    ) -> QueueAction | None:
        """
        Moves to the door spot.
        Afterwards, we expect to change map. It's easier to block all other generators
        to avoid interference, although it may not be the best solution. # TODO - review
        :param nodes: "Safe" nodes where it's safe to cast a door.
        :return:
        """
        if getattr(self, 'door_target', None) is None:
            if nodes is None:
                # if not specified for generator, check if specified by minimap obj
                nodes = self.data.current_minimap.door_spot
            if nodes is None:
                # Otherwise, use current position
                nodes = [self.data.current_minimap_position]
            target = random.choice(nodes)
            setattr(self, "door_target", target)

            # Create a connection to (0, 0), which is a void node used to represent town
            minimap = self.data.current_minimap
            minimap.grid.node(*target).connect(
                minimap.grid.node(0, 0), MinimapConnection.PORTAL
            )  # TODO - Don't forget to remove connection afterwards once done

        self.data.update(next_target=getattr(self, "door_target"))
        self.generator.block_generators("Maintenance", id(self.generator))
        self.generator.block_generators("AntiDetection", id(self.generator))

    def _trigger_discord_alert(self) -> QueueAction:
        space_left = getattr(self, "_space_left")
        if space_left <= getattr(self, "space_left_alert"):
            setattr(self, "current_step", getattr(self, "current_step") + 1)
            return QueueAction(
                identifier="Inventory Full - Discord Alert",
                priority=1,
                user_message=[f"{space_left} slots left in inventory."],
            )

    def _use_nearest_town_scroll(self) -> QueueAction | None:
        raise NotImplementedError

    def _ensure_in_town(self) -> QueueAction | None:
        pass

    def _move_to_shop_portal(self, target: tuple[int, int]):
        return self._move_to_door(target)

    def _enter_shop_portal(self, target: tuple[int, int]):
        return self._enter_door(target)

    def _find_npc(self, npc_name: str) -> QueueAction | None:
        pass

    def _click_npc(self, npc_name: str) -> QueueAction | None:
        pass

    def _ensure_in_tab(self, tab_name: str) -> QueueAction | None:
        pass

    def _sell_items(self) -> QueueAction | None:
        pass


class InventoryActions:
    @staticmethod
    def toggle(generator: DecisionGenerator, key: str) -> QueueAction:
        generator.blocked = True
        return QueueAction(
            identifier=f"Toggling {generator.data.ign} Inventory Menu",
            priority=5,
            action=partial(controller.press, generator.data.handle, key, silenced=True),
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )

    @staticmethod
    def expand_inventory_menu(generator: DecisionGenerator) -> QueueAction:
        generator.blocked = True
        box = generator.data.inventory_menu.get_abs_box(
            generator.data.handle, generator.data.inventory_menu.extend_button
        )
        target = box.random()

        return QueueAction(
            identifier=f"Expanding {generator.data.ign} Inventory Menu",
            priority=5,
            action=partial(
                InventoryActions._mouse_move_and_click, generator.data.handle, target
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )

    @staticmethod
    def switch_tab(generator: DecisionGenerator, nbr_presses: int) -> QueueAction:
        generator.blocked = True

        return QueueAction(
            identifier=f"Tabbing {generator.data.ign} Inventory {nbr_presses} times",
            priority=5,
            action=partial(
                InventoryActions._press_n_times,
                generator.data.handle,
                "tab",
                nbr_presses,
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )

    @staticmethod
    async def _press_n_times(handle: int, key: str, nbr_of_presses: int = 1):
        for _ in range(nbr_of_presses):
            await controller.press(handle, key, silenced=True)

    @staticmethod
    async def _mouse_move_and_click(handle: int, point: tuple[int, int]):
        await controller.mouse_move(handle, point)
        await controller.click(handle)
        await controller.mouse_move(handle, (-1000, 1000))

    @staticmethod
    def _move_to_door(
        generator: DecisionGenerator, target: tuple[int, int]
    ) -> QueueAction | None:
        """Use this to go in door vicinity, if not already there"""
        while ...:
            actions = get_to_target(
                self.data.current_minimap_position, target, self.data.current_minimap
            )

    @staticmethod
    def _enter_door(
        generator: DecisionGenerator, target: tuple[int, int]
    ) -> QueueAction | None:
        """Use this once already in door vicinity, to try and enter"""
        pass
