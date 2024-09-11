import asyncio
import cv2
import logging
import math
import multiprocessing.connection
import multiprocessing.managers
import numpy as np
import os
import random
from botting import controller, PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from botting.utilities import Box, find_image
from paths import ROOT
from royals.actions import toggle_inventory, expand_inventory, priorities
from royals.actions.skills_related_v2 import cast_skill_single_press
from royals.constants import (
    INVENTORY_DISCORD_ALERT,
    INVENTORY_CLEANUP_WITH_TOWN_SCROLL,
    INVENTORY_CLEANUP_WITH_SELF_DOOR,
    INVENTORY_CLEANUP_WITH_PARTY_DOOR,
)
from royals.model.maps import RoyalsMap
from royals.model.mechanics import MinimapConnection
from .mixins import MenusMixin, NextTargetMixin, MovementsMixin, MinimapAttributesMixin

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO


class InventoryManager(
    MenusMixin, NextTargetMixin, MovementsMixin, MinimapAttributesMixin, DecisionMaker
):
    # TODO - Add NPC'ing of ETC items as well
    _throttle = 180
    _TIME_LIMIT = 300
    _DISTANCE_TO_DOOR_THRESHOLD = 2
    TABS_OFFSETS = {
        "Equip": Box(left=84, right=55, top=90, bottom=35, offset=True),
        "Use": Box(left=128, right=99, top=90, bottom=35, offset=True),
        "Set-up": Box(left=172, right=143, top=90, bottom=35, offset=True),
        "Etc": Box(left=216, right=187, top=90, bottom=35, offset=True),
        "Cash": Box(left=260, right=231, top=90, bottom=35, offset=True),
    }
    ACTIVE_TAB_COLOR = np.array([136, 102, 238])
    SELECTED_ITEM_COLOR = np.array([34, 153, 238])
    FIRST_SLOT_SHOP_OFFSET: Box = Box(
        left=135, right=160, top=124, bottom=80, offset=True
    )
    SELL_BUTTON_OFFSET: Box = Box(left=268, right=227, top=34, bottom=-30, offset=True)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        cleanup_procedure: int,
        space_left_trigger: int = 97,
        target_tab: str = "Equip",
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe, **kwargs)
        # Set a condition but use a standard Lock instead of RLock, allowing to use
        # basic lock mechanism as well
        temp_lock = self.request_proxy(metadata, f"{self}", "Lock")
        self._condition = DecisionMaker.request_proxy(
            metadata, f"{self}", "Condition", False, temp_lock
        )
        self._cleanup_procedure = cleanup_procedure
        self._space_left_trigger = space_left_trigger
        self._target_tab = target_tab

        # Inventory Attributes
        self._create_inventory_menu_attributes()

        # Attributes for different procedures
        self._door_spot: tuple[int, int] | None = None
        self._npc_positions: list[tuple[int, int]] | None = None
        self._open_shop_img = cv2.imread(
            os.path.join(ROOT, "royals/assets/detection_images/Open NPC Shop.png")
        )
        self._open_shop_box: Box | None = None

    async def _decide(self, *args, **kwargs) -> None:
        space_left = await asyncio.wait_for(self._check_inventory_space(), timeout=10)
        await self._ensure_inventory_displayed(displayed=False)
        if space_left < self._space_left_trigger:
            await self._trigger_procedure()

    async def _check_inventory_space(self) -> int:
        try:
            await self._ensure_inventory_displayed()
            await self._ensure_inventory_extended()
            await self._ensure_on_target_tab()
            return await self._get_space_left()
        except AssertionError:
            logger.log(LOG_LEVEL, f"Failed to check inventory space. Retrying once")
            await self._check_inventory_space()
        except Exception as e:
            logger.error(f"Exception occurred in {self}: {e}.")
            raise e

    async def _ensure_inventory_displayed(self, displayed: bool = True) -> None:
        request = ActionRequest(
            f"{self} - Toggling Inventory On",
            toggle_inventory,
            self.data.ign,
            priorities.INVENTORY_CHECKUP,
            args=(self.data.handle, self.data.ign),
        )
        if displayed:
            await self._validate_request_async(
                request,
                lambda: self.data.inventory_menu.is_displayed(
                    self.data.handle, self.data.current_client_img
                ),
                timeout=10.0,
            )
        else:
            await self._validate_request_async(
                request,
                lambda: not self.data.inventory_menu.is_displayed(
                    self.data.handle, self.data.current_client_img
                ),
                timeout=10.0,
            )
        self.data.update_attribute("inventory_menu_displayed")

    async def _ensure_inventory_extended(self) -> None:
        if not self.data.inventory_menu_displayed:
            await self._ensure_inventory_displayed()

        target = self.data.inventory_menu.get_abs_box(
            self.data.handle, self.data.inventory_menu.extend_button
        ).random()

        request = ActionRequest(
            f"{self} - Expanding Inventory",
            expand_inventory,
            self.data.ign,
            priorities.INVENTORY_CHECKUP,
            args=(self.data.handle, target),
        )
        await self._validate_request_async(
            request,
            lambda: self.data.inventory_menu.is_extended(
                self.data.handle, self.data.current_client_img
            ),
            timeout=10.0,
        )
        self.data.update_attribute("inventory_menu_extended")

    async def _ensure_on_target_tab(self) -> None:
        if not self.data.inventory_menu_extended:
            await self._ensure_inventory_extended()

        request = ActionRequest(
            f"{self} - Switching to Target Tab",
            controller.press,
            self.data.ign,
            priorities.INVENTORY_CHECKUP,
            args=(self.data.handle, "tab"),
            kwargs=dict(silenced=True, nbr_times=1, delay=0.25),
        )
        await self._validate_request_async(
            request,
            lambda: self.data.inventory_menu.get_active_tab(
                self.data.handle, self.data.current_client_img
            )
            == self._target_tab,
            timeout=10.0,
        )
        self.data.update_attribute("inventory_menu_active_tab")

    async def _get_space_left(self) -> int:
        if not self.data.inventory_menu_active_tab == self._target_tab:
            await self._ensure_on_target_tab()

        self.data.update_attribute("inventory_space_left")
        return self.data.inventory_space_left

    async def _trigger_procedure(self) -> None:
        if self._cleanup_procedure == INVENTORY_DISCORD_ALERT:
            self.pipe.send(self._discord_alert())
        else:
            self._disable_decision_makers(
                "MobsHitting",
                "TelecastMobsHitting",
                "PartyRebuff",
                "SoloRebuff",
                "PetFood",
                "MountFood"
            )
            if self._cleanup_procedure == INVENTORY_CLEANUP_WITH_TOWN_SCROLL:
                await self._cleanup_with_town_scroll()
            elif self._cleanup_procedure == INVENTORY_CLEANUP_WITH_SELF_DOOR:
                await asyncio.wait_for(
                    self._cleanup_with_self_door(), timeout=self._TIME_LIMIT
                )
            elif self._cleanup_procedure == INVENTORY_CLEANUP_WITH_PARTY_DOOR:
                await self._cleanup_with_party_door()
            else:
                raise ValueError(f"Unknown procedure: {self._cleanup_procedure}")

    async def _discord_alert(self) -> ActionRequest:
        return ActionRequest(
            f"{self} - Discord Alert",
            asyncio.sleep,
            self.data.ign,
            priorities.INVENTORY_CHECKUP,
            args=(0,),
            discord_request=DiscordRequest(
                msg=f"{self.data.ign} only has {self.data.inventory_space_left} "
                f"inventory space left",
            ),
        )

    async def _cleanup_with_town_scroll(self) -> None:
        raise NotImplementedError

    async def _cleanup_with_self_door(self) -> None:
        logger.log(LOG_LEVEL, f"{self} is cleaning up with SELF DOOR")
        self._setup_procedure()
        while True:
            try:
                await asyncio.wait_for(self._move_to_town_self_door(), timeout=20.0)
                self._setup_new_map()
                break
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                breakpoint()

        while not self._confirm_shop_open():
            self._enable_decision_makers("Rotation")
            await self._move_to_npc_shop()
            self._disable_decision_makers("Rotation")
            await asyncio.sleep(0.5)
            await self._toggle_npc_shop()

        logger.log(LOG_LEVEL, f"{self} has reached and opened NPC Shop")
        await self._activate_tab()
        await self._clear_inventory()
        logger.log(LOG_LEVEL, f"{self} inventory has been cleared")
        while self._confirm_shop_open():
            await self._toggle_npc_shop(opening=False)
            await asyncio.sleep(0.5)

        self._enable_decision_makers("Rotation")
        while True:
            try:
                await asyncio.wait_for(self._move_back_to_original_map(), timeout=20.0)
                self._setup_new_map(towards_town=False)
                self._reset_all()
                break
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                breakpoint()
        logger.log(LOG_LEVEL, f"{self} procedure completed")

    def _setup_procedure(self) -> None:
        # TODO - Implement grid connections
        assert self.data.has_pathing_attributes
        assert self.data.has_minimap_attributes
        # Overwrite action mechanics to ensure keys are always released
        self.data.create_attribute("action", self._always_release_keys_on_actions)

        door_spot = getattr(
            self.data.current_minimap, "door_spot", [self.data.current_minimap_position]
        )
        self._door_spot = random.choice(door_spot)

    def _reset_all(self):
        self._door_spot = self._npc_positions = self._open_shop_box = None
        self._create_pathing_attributes(self.data.action_duration)
        self._create_rotation_attributes(self.data.feature_cycle)
        self.data.next_target = self.data.current_minimap_position
        self._enable_decision_makers(
            "MobsHitting",
            "TelecastMobsHitting",
            "PartyRebuff",
            "SoloRebuff",
            "PetFood",
            "MountFood",
            "Rotation"
        )

    async def _move_to_town_self_door(self):
        await self._move_to_door_spot()
        logger.log(LOG_LEVEL, f"{self} has reached door_spot")

        # Refresh door spot to current position
        grid = self.data.current_minimap.grid
        while True:
            target = self.data.current_minimap_position
            if grid.node(*target).walkable:
                break
            await asyncio.sleep(0.1)
        self._connect_door_to_other_map(target)

        await self._cast_door()
        await self._enter_door()
        await self._confirm_in_map(self.data.current_map.path_to_shop)
        logger.log(LOG_LEVEL, f"{self} has reached town")

    async def _move_back_to_original_map(self):
        await self._move_to_door_spot()
        self._connect_door_to_other_map()
        await self._enter_door()
        self.data.update_attribute('current_map')
        await self._confirm_in_map(self.data.current_map)

    async def _cleanup_with_party_door(self) -> None:
        raise NotImplementedError

    async def _move_to_door_spot(self) -> None:
        self._set_fixed_target(self._door_spot)
        await self._wait_until_target_reached()

    async def _wait_until_target_reached(self) -> None:
        while True:
            if math.dist(
                self.data.current_minimap_position, self.data.next_target
            ) < self._DISTANCE_TO_DOOR_THRESHOLD:
                break
            await asyncio.sleep(0.5)

    def _connect_door_to_other_map(self, target: tuple[int, int] = None) -> None:
        target = target or self._door_spot
        grid = self.data.current_minimap.grid
        # Use current spot as the more precise door spot
        self._set_fixed_target(target)
        grid.node(*self.data.next_target).connect(
            grid.node(0, 0), MinimapConnection.PORTAL
        )

    async def _cast_door(self) -> None:
        # TODO - implement validation mechanism to ensure door is properly cast.
        # Use door image from game files and find a matchTemplate threshold acceptable
        # Create a PORTAL connection to (0, 0) and attempt to move there
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Casting Door",
                cast_skill_single_press,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                cancel_tasks=[f"Rotation({self.data.ign})"],
                args=(
                    self.data.handle,
                    self.data.ign,
                    self.data.character.skills["Mystic Door"],
                ),
                callbacks=[self._condition.release],
            )
        )

    async def _enter_door(self) -> None:
        # Use the temporary connection as next target
        self._set_fixed_target((0, 0))

        def _temp_minimap_pos():
            try:
                return self._get_minimap_pos()
            except Exception as e:
                return 0, 0

        # Overwrite the current_minimap_position attribute to disable the error handler
        self.data.create_attribute(
            "current_minimap_position",
            _temp_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
            error_handler=None,
        )

        # Wait until the minimap changes - should be indicator that the map has changed
        await self._wait_until_minimap_changes()

    async def _wait_until_minimap_changes(self) -> None:
        current_box = self.data.current_entire_minimap_box
        while True:
            self.data.update_attribute("current_entire_minimap_box")
            if current_box != self.data.current_entire_minimap_box:
                self._disable_decision_makers("Rotation")
                break
            await asyncio.sleep(0.5)

    async def _confirm_in_map(self, map_inst: RoyalsMap) -> None:
        minimap = map_inst.minimap
        while True:
            if minimap.validate_in_map(self.data.handle):
                break
            await asyncio.sleep(0.5)

    def _setup_new_map(self, towards_town: bool = True) -> None:
        # Remove the temporary PORTAL connection
        grid = self.data.current_minimap.grid
        grid.node(*self._door_spot).connections.pop(-1)
        if towards_town:
            self.data.current_map = self.data.current_map.path_to_shop

        self.data.update_attribute("current_minimap")
        # This will effectively refresh all minimap attributes
        self._create_minimap_attributes()
        self.data.update_attribute("movement_handler")

    async def _move_to_npc_shop(self) -> None:
        if self.data.current_map.path_to_shop is not None:
            raise NotImplementedError(
                "TODO - Implement iterative algo for each map that has path to shop"
            )
        self._door_spot = self.data.current_minimap_position
        self._npc_positions = self.data.current_minimap.get_character_positions(
            self.data.handle, "NPC", self.data.current_client_img
        )
        self._set_fixed_target(self.data.current_minimap.npc_shop)
        await self._wait_until_target_reached()

    def _confirm_shop_open(self) -> bool:
        with self._condition:
            match = find_image(self.data.current_client_img, self._open_shop_img)
            res = len(match) > 0
            if res:
                self._open_shop_box = match.pop()
        return res

    async def _toggle_npc_shop(self, opening: bool = True) -> None:
        key = controller.key_binds(self.data.ign)["NPC Chat"] if opening else "escape"
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Toggling NPC Shop {opening}",
                controller.press,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                args=(self.data.handle, key),
                kwargs=dict(delay=1.0, silenced=True),
                callbacks=[self._condition.release],
            )
        )

    async def _activate_tab(self):
        box: Box = self.TABS_OFFSETS[self._target_tab] + self._open_shop_box
        box_img = box.extract_client_img(self.data.current_client_img)
        binary_img = cv2.inRange(box_img, self.ACTIVE_TAB_COLOR, self.ACTIVE_TAB_COLOR)
        if np.count_nonzero(binary_img) < 10:
            await asyncio.to_thread(self._condition.acquire)
            target = box.random()
            self.pipe.send(
                ActionRequest(
                    f"{self} - Opening NPC Shop",
                    controller.mouse_move_and_click,
                    priorities.INVENTORY_CLEANUP,
                    block_lower_priority=True,
                    args=(self.data.handle, target),
                    kwargs=dict(delay=1.0),
                    callbacks=[self._condition.release],
                )
            )

    async def _clear_inventory(self):
        await self._click_on_first_item()
        await self._mouse_move_to_sell_button()
        while self.active_item_detected():
            await self._click_on_sell_button()
            await self._confirm_sale()

    async def _click_on_first_item(self):
        box = self.FIRST_SLOT_SHOP_OFFSET + self._open_shop_box
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Clicking on First Item",
                controller.mouse_move_and_click,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                args=(self.data.handle, box.random()),
                callbacks=[self._condition.release],
            )
        )

    def active_item_detected(self) -> bool:
        box = self.FIRST_SLOT_SHOP_OFFSET + self._open_shop_box
        self.data.update_attribute('current_client_img')
        box_img = box.extract_client_img(self.data.current_client_img)
        binary_img = cv2.inRange(
            box_img, self.SELECTED_ITEM_COLOR, self.SELECTED_ITEM_COLOR
        )
        print(np.count_nonzero(binary_img) / binary_img.size)
        return np.count_nonzero(binary_img) / binary_img.size > 0.1

    async def _mouse_move_to_sell_button(self):
        button = self.SELL_BUTTON_OFFSET + self._open_shop_box
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Moving to Sell Button",
                controller.mouse_move,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                args=(self.data.handle, button.random()),
                callbacks=[self._condition.release],
            )
        )

    async def _click_on_sell_button(self):
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Clicking on Sell Button",
                controller.click,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                args=(self.data.handle, ),
                kwargs=dict(delay=0.1),
                callbacks=[self._condition.release],
            )
        )

    async def _confirm_sale(self):
        await asyncio.to_thread(self._condition.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Clicking on Sell Button",
                controller.press,
                priorities.INVENTORY_CLEANUP,
                block_lower_priority=True,
                args=(self.data.handle, "y"),
                kwargs=dict(delay=0.1),
                callbacks=[self._condition.release],
            )
        )
