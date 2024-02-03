from functools import partial
from botting.core import DecisionGenerator, GeneratorUpdate, QueueAction, controller
from royals.game_data import MaintenanceData
from royals.models_implementations.mechanics.path_into_movements import get_to_target


class InventoryChecks:
    """
    Utility class for InventoryManager.
    Defines all methods used for inventory management.
    """
    def __init__(self,
                 generator: DecisionGenerator,
                 toggle_key: str) -> None:
        self.generator = generator
        self.data: MaintenanceData = generator.data
        self._key = toggle_key

    def ensure_is_displayed(self) -> QueueAction | None:
        if not self.data.inventory_menu.is_displayed(
                self.data.handle, self.data.current_client_img
        ):
            return InventoryActions.toggle(self.generator, self._key)

    def ensure_is_extended(self) -> QueueAction | None:
        if self.data.inventory_menu.is_displayed(
            self.data.handle, self.data.current_client_img
        ):
            if not self.data.inventory_menu.is_extended(
                self.data.handle, self.data.current_client_img
            ):
                return InventoryActions.expand_inventory_menu(self.generator)
        else:
            return self.ensure_is_displayed()

    def ensure_proper_tab(self, tab_to_watch: str) -> QueueAction | None:
        if self.data.inventory_menu.is_extended(
            self.data.handle, self.data.current_client_img
        ):
            active_tab = self.data.inventory_menu.get_active_tab(
                self.data.handle, self.data.current_client_img
            )
            if active_tab is None:
                self.generator._fail_count += 1  # TODO - clean this up, should not return None
                return
            elif active_tab != tab_to_watch:
                nbr_presses = self.data.inventory_menu.get_tab_count(
                    active_tab, tab_to_watch
                )
                return InventoryActions.switch_tab(self.generator, nbr_presses)

        else:
            return self.ensure_is_extended()

    def get_space_left(self, tab_to_watch: str) -> int:
        active_tab = self.data.inventory_menu.get_active_tab(
            self.data.handle, self.data.current_client_img
        )
        if active_tab == tab_to_watch:
            space_left = self.data.inventory_menu.get_space_left(
                self.data.handle, self.data.current_client_img
            )
            logger.info(f"Inventory space left: {space_left}")
            return space_left

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
            action=partial(
                controller.press, generator.data.handle, key, silenced=True
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator),
                generator_kwargs={"blocked": False}
            )
        )

    @staticmethod
    def expand_inventory_menu(generator: DecisionGenerator) -> QueueAction:
        generator.blocked = True
        box = generator.data.inventory_menu.get_abs_box(
            generator.data.handle, generator.data.inventory_menu.extend_button
        )
        target = box.random()

        async def _mouse_move_and_click(handle: int, point: tuple[int, int]):
            await controller.mouse_move(handle, point)
            await controller.click(handle)
            await controller.mouse_move(handle, (-1000, 1000))

        return QueueAction(
            identifier=f"Expanding {generator.data.ign} Inventory Menu",
            priority=5,
            action=partial(
                _mouse_move_and_click, generator.data.handle, target
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator),
                generator_kwargs={"blocked": False}
            )
        )

    @staticmethod
    def switch_tab(generator: DecisionGenerator, nbr_presses: int) -> QueueAction:
        generator.blocked = True

        async def _press_n_times(handle: int, key: str, nbr_of_presses: int = 1):
            for _ in range(nbr_of_presses):
                await controller.press(handle, key, silenced=True)

        return QueueAction(
            identifier=f"Tabbing {generator.data.ign} Inventory {nbr_presses} times",
            priority=5,
            action=partial(
                _press_n_times, generator.data.handle, "tab", nbr_presses
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator),
                generator_kwargs={"blocked": False}
            )
        )

    @staticmethod
    def _move_to_door(
            generator: DecisionGenerator,
            target: tuple[int, int]
    ) -> QueueAction | None:
        """Use this to go in door vicinity, if not already there"""
        while ...:
            actions = get_to_target(self.data.current_minimap_position,
                                    target,
                                    self.data.current_minimap)

    @staticmethod
    def _enter_door(
            generator: DecisionGenerator, target: tuple[int, int]
    ) -> QueueAction | None:
        """Use this once already in door vicinity, to try and enter"""
        pass
