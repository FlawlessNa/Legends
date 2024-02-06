import logging
import math
import random
import time
from functools import partial
from typing import Union

from botting import PARENT_LOG
from botting.core import DecisionGenerator, GeneratorUpdate, QueueAction, controller
from royals.actions import cast_skill, continuous_teleport
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
        # TODO - Might make more sense to take advantage of Rotation generator due to all
        the failsafes already in place. CONFIRM
        Takes full control of character movement during this time, so the Rotation
        and Maintenance generators are disabled.
        :param nodes: "Safe" nodes where it's reliable to cast a door.
        :return:
        """
        if getattr(self, "door_target", None) is None:
            if nodes is None:
                # if not specified for generator, check if specified by minimap obj
                nodes = getattr(self.data.current_minimap, "door_spot", None)
            if nodes is None:
                # Otherwise, use current position
                nodes = [self.data.current_minimap_position]
            target = random.choice(nodes)
            setattr(self, "door_target", target)
            self.generator.block_generators("All", id(self.generator))

        if (
            math.dist(self.data.current_minimap_position, getattr(self, "door_target"))
            > 2
        ):
            return InventoryActions.move_to_target(
                self.generator, getattr(self, "door_target"), "Moving to Door Spot"
            )

    def _use_mystic_door(self) -> QueueAction | None:
        """
        Uses Mystic Door skill.
        # TODO - Implement a failsafe to confirm door is indeed casted
        (Pre-read nbr of mystic rocks and ensure one has been used).
        :return:
        """
        setattr(self, "door_target", self.data.current_minimap_position)
        setattr(self, "current_step", getattr(self, "current_step") + 1)
        # Create a connection to (0, 0), which is a void node used to represent town
        minimap = self.data.current_minimap
        minimap.grid.node(*self.data.current_minimap_position).connect(
            minimap.grid.node(0, 0), MinimapConnection.PORTAL
        )  # TODO - Don't forget to remove connection afterwards once done

        return InventoryActions.use_mystic_door(self.generator)

    def _enter_door(self) -> QueueAction | None:
        if self.data.current_minimap_position is not None:
            return InventoryActions.move_to_target(
                self.generator, (0, 0), "Entering Door"
            )

    def _move_to_shop(self) -> QueueAction | None:
        # breakpoint()
        if self.data.current_map.path_to_shop is not None:
            # We need to actually go into a shop from town
            raise NotImplementedError("TODO")

        # Manually update for new minimap
        self.data.update("current_minimap_area_box", "minimap_grid")
        self.data.update(
            current_minimap_position=self.data.current_minimap.get_character_positions(
                self.data.handle,
                client_img=self.data.current_client_img,
                map_area_box=self.data.current_minimap_area_box,
            ).pop()
        )
        target = self.data.current_minimap.npc_shop

        if math.dist(self.data.current_minimap_position, target) > 10:
            return InventoryActions.move_to_target(
                self.generator, target, "Moving to Shop", enable_multi=True
            )

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
    def toggle(
        generator: DecisionGenerator, key: str, game_data_args=tuple()
    ) -> QueueAction:
        generator.blocked = True
        return QueueAction(
            identifier=f"Toggling {generator.data.ign} Menu",
            priority=5,
            action=partial(controller.press, generator.data.handle, key, silenced=True),
            update_generators=GeneratorUpdate(
                generator_id=id(generator),
                generator_kwargs={"blocked": False},
                game_data_args=game_data_args,
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
    def use_mystic_door(
        generator: DecisionGenerator,
    ) -> QueueAction:
        generator.blocked = True
        return QueueAction(
            identifier=f"Using Mystic Door",
            priority=5,
            action=partial(
                cast_skill,
                generator.data.handle,
                generator.data.ign,
                generator.data.character.skills["Mystic Door"],
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )

    @staticmethod
    def move_to_target(
        generator: DecisionGenerator,
        target: tuple[int, int],
        identifier: str,
        enable_multi: bool = False,
    ) -> QueueAction:
        actions = get_to_target(
            generator.data.current_minimap_position,
            target,
            generator.data.current_minimap,
        )
        res = None
        if actions and enable_multi and actions[0].func.__name__ == "teleport_once":
            num_actions = 0
            for action in actions:
                if action == actions[0]:
                    num_actions += 1
                else:
                    break
            res = partial(
                continuous_teleport,
                generator.data.handle,
                generator.data.ign,
                actions[0].keywords["direction"],
                generator.data.character.skills["Teleport"],
                num_actions,
            )

        elif actions:
            first_action = actions[0]
            args = (
                generator.data.handle,
                generator.data.ign,
                first_action.keywords["direction"],
            )
            kwargs = first_action.keywords.copy()
            kwargs.pop("direction", None)
            if first_action.func.__name__ == "teleport_once":
                kwargs.update(
                    teleport_skill=generator.data.character.skills["Teleport"]
                )
            res = partial(first_action.func, *args, **kwargs)

        return QueueAction(
            identifier=identifier,
            priority=5,
            action=res,
        )
