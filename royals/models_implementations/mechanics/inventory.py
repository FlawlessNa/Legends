import asyncio
import cv2
import logging
import os
import math
import numpy as np
import random
import time
from functools import partial
from typing import Union

from botting import PARENT_LOG
from botting.core import DecisionGenerator, GeneratorUpdate, QueueAction, controller
from botting.utilities import Box, find_image
from paths import ROOT
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

    tabs_offsets = {
        "Equip": Box(left=130, right=55, top=90, bottom=35, offset=True),
        "Use": Box(left=174, right=99, top=90, bottom=35, offset=True),
        "Set-up": Box(left=218, right=143, top=90, bottom=35, offset=True),
        "Etc": Box(left=262, right=187, top=90, bottom=35, offset=True),
        "Cash": Box(left=306, right=231, top=90, bottom=35, offset=True),
    }
    active_color = np.array([136, 102, 238])
    first_shop_slot_offset: Box = Box(
        left=135, right=160, top=124, bottom=80, offset=True
    )
    sell_button_offset: Box = Box(left=268, right=227, top=34, bottom=-30, offset=True)

    def __init__(
        self,
        generator: DecisionGenerator,
        data: Union[MaintenanceData, MinimapData],
        toggle_key: str,
        npc_shop_key: str,
    ) -> None:
        self.generator: DecisionGenerator = generator
        self.data: Union[MaintenanceData, MinimapData] = data
        self._key = toggle_key
        self._npc_shop_key = npc_shop_key

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
            if space_left > getattr(self, "space_left_alert"):
                setattr(self, "current_step", getattr(self, "num_steps"))

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
        time.sleep(1.5)

    def _move_to_shop(self) -> QueueAction | None:
        if self.data.current_map.path_to_shop is not None:
            # We need to actually go into a shop from town
            raise NotImplementedError("TODO")

        if not hasattr(self, "return_door_target"):
            # Manually update all data new minimap
            self.data.update("current_minimap_area_box", "minimap_grid")
            self.data.update(
                current_minimap_position=self.data.current_minimap.get_character_positions(
                    self.data.handle,
                    client_img=self.data.current_client_img,
                    map_area_box=self.data.current_minimap_area_box,
                ).pop()
            )
            # Update door position as well as all npcs seen at initial position.
            # This is used to counteract fact that minimap is not "fixed" in most towns
            setattr(self, "return_door_target", self.data.current_minimap_position)
            npcs_positions = self.data.current_minimap.get_character_positions(
                self.data.handle,
                "NPC",
                self.data.current_client_img,
                map_area_box=self.data.current_minimap_area_box,
            )
            setattr(self, "npcs_positions", npcs_positions)

        target = self.data.current_minimap.npc_shop

        if math.dist(self.data.current_minimap_position, target) > 7:
            return InventoryActions.move_to_target(
                self.generator, target, "Moving to Shop", enable_multi=True
            )

    def _open_npc_shop(self) -> QueueAction | None:
        shop_img_needle = cv2.imread(
            os.path.join(ROOT, "royals/assets/detection_images/Open NPC Shop.png")
        )
        match = find_image(self.data.current_client_img, shop_img_needle)
        if len(match) == 0:
            self.blocked = True
            return QueueAction(
                identifier="Opening Shop",
                priority=5,
                action=partial(
                    controller.press,
                    self.data.handle,
                    self._npc_shop_key,
                    silenced=True,
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self.generator), generator_kwargs={"blocked": False}
                ),
            )
        else:
            setattr(self, "_shop_open_box", match[0])

    def _activate_tab(self, tab_name: str) -> QueueAction | None:
        box: Box = self.tabs_offsets[tab_name] + getattr(self, "_shop_open_box")
        box_img = box.extract_client_img(self.data.current_client_img)
        binary_img = cv2.inRange(box_img, self.active_color, self.active_color)
        if np.count_nonzero(binary_img) < 10:
            return InventoryActions.switch_shop_tab(self.generator, box.random())

    def _cleanup_inventory(self) -> QueueAction | None:
        if getattr(self, "_space_left") < 96:
            box = self.first_shop_slot_offset + getattr(self, "_shop_open_box")
            num_clicks = 96 - getattr(self, "_space_left")
            button = self.sell_button_offset + getattr(self, "_shop_open_box")
            return InventoryActions.sell_items(
                self.generator, box.random(), button.random(), num_clicks
            )

    def _close_npc_shop(self) -> QueueAction | None:
        shop_img_needle = cv2.imread(
            os.path.join(ROOT, "royals/assets/detection_images/Open NPC Shop.png")
        )
        match = find_image(self.data.current_client_img, shop_img_needle)
        if len(match) > 0:
            self.blocked = True
            return QueueAction(
                identifier="Closing Shop",
                priority=5,
                action=partial(
                    controller.press,
                    self.data.handle,
                    "escape",
                    silenced=True,
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self.generator), generator_kwargs={"blocked": False}
                ),
            )
        else:
            delattr(self, "_shop_open_box")

    def _return_to_door(self) -> QueueAction | None:
        curr_pos = self.data.current_minimap_position
        if curr_pos is None:
            time.sleep(1.5)
            return
        target = getattr(self, "return_door_target")
        if math.dist(curr_pos, target) > 2:
            setattr(
                self,
                "_direction",
                "right" if curr_pos[0] < target[0] else "left",
            )
            return InventoryActions.move_to_target(
                self.generator,
                getattr(self, "return_door_target"),
                "Returning to Door",
                enable_multi=True,
            )

        # If we reached the "central node" in minimap but are not yet at door, we need
        # to compare the initial positions of the NPCs with current and move based on
        # that.
        current_npcs = self.data.current_minimap.get_character_positions(
            self.data.handle,
            "NPC",
            self.data.current_client_img,
            map_area_box=self.data.current_minimap_area_box,
        )
        initial_npcs = getattr(self, "npcs_positions")
        if len(current_npcs) != len(initial_npcs):
            direction = getattr(self, "_direction")
            target = (
                (curr_pos[0] + 10, curr_pos[1])
                if direction == "right"
                else (
                    curr_pos[0] - 10,
                    curr_pos[1],
                )
            )
            return InventoryActions.move_to_target(
                self.generator,
                target,
                "Returning to Door",
            )
        else:
            horiz_dist = sum(
                (current_npcs[i][0] - initial_npcs[i][0])
                for i in range(len(current_npcs))
            ) / len(current_npcs)

            self.blocked = True
            return QueueAction(
                identifier="Re-entering in Door",
                priority=5,
                action=partial(
                    controller.move,
                    self.data.handle,
                    self.data.ign,
                    "right" if horiz_dist > 0 else "left",
                    horiz_dist / self.data.current_minimap.minimap_speed,
                    "up",
                ),
                update_generators=GeneratorUpdate(
                    generator_id=id(self.generator), generator_kwargs={"blocked": False}
                ),
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
    async def _mouse_move_and_click(
        handle: int, point: tuple[int, int], move_away: bool = True
    ):
        await controller.mouse_move(handle, point)
        await controller.click(handle)
        if move_away:
            await controller.mouse_move(handle, (-1000, 1000))

    @staticmethod
    def switch_shop_tab(generator: DecisionGenerator, target: tuple[int, int]):
        generator.blocked = True
        return QueueAction(
            identifier=f"Switching Shop Tab",
            priority=5,
            action=partial(
                InventoryActions._mouse_move_and_click, generator.data.handle, target
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )

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
    def sell_items(
        generator: DecisionGenerator,
        target: tuple[int, int],
        sell_button: tuple[int, int],
        num_clicks: int,
    ) -> QueueAction:
        generator.blocked = True
        return QueueAction(
            identifier=f"Selling Items",
            priority=90,
            is_cancellable=True,
            action=partial(
                InventoryActions._clear_inventory,
                generator.data.handle,
                target,
                sell_button,
                num_clicks,
            ),
            update_generators=GeneratorUpdate(
                generator_id=id(generator),
                generator_kwargs={"blocked": False},
                generator_attribute="_slots_cleaned",
            ),
        )

    @staticmethod
    async def _clear_inventory(
        handle: int,
        target_tab: tuple[int, int],
        sell_button: tuple[int, int],
        num_clicks: int,
    ) -> int:
        res = 0
        # TODO - Deal with cancellations?
        await InventoryActions._mouse_move_and_click(
            handle, target_tab, move_away=False
        )
        await controller.mouse_move(handle, sell_button, total_duration=0.2)
        await asyncio.sleep(0.1)
        for _ in range(num_clicks):
            res += await controller.click(handle, nbr_times=1)
            await asyncio.sleep(0.1)
            await controller.press(handle, "y", silenced=False)
            await asyncio.sleep(0.1)
        return res

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

        generator.blocked = True
        return QueueAction(
            identifier=identifier,
            priority=5,
            action=res,
            update_generators=GeneratorUpdate(
                generator_id=id(generator), generator_kwargs={"blocked": False}
            ),
        )
