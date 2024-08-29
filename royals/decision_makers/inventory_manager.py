import asyncio
import logging
import math
import multiprocessing.connection
import multiprocessing.managers
import random
from botting import controller, PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from royals.actions import toggle_inventory, expand_inventory, priorities
from royals.actions.skills_related_v2 import cast_skill_single_press
from royals.constants import (
    INVENTORY_DISCORD_ALERT,
    INVENTORY_CLEANUP_WITH_TOWN_SCROLL,
    INVENTORY_CLEANUP_WITH_SELF_DOOR,
    INVENTORY_CLEANUP_WITH_PARTY_DOOR,
)
from royals.model.mechanics import MinimapConnection
from .mixins import MenusMixin, NextTargetMixin, MovementsMixin, MinimapAttributesMixin

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO


class InventoryManager(
    MenusMixin, NextTargetMixin, MovementsMixin, MinimapAttributesMixin, DecisionMaker
):
    _throttle = 180
    _TIME_LIMIT = 300
    _DISTANCE_TO_DOOR_THRESHOLD = 2

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
        await self._get_to_door_spot()
        logger.log(LOG_LEVEL, f"{self} has reached door_spot")
        await self._cast_door()
        await self._enter_door()
        logger.log(LOG_LEVEL, f"{self} has reached town")
        await self._move_to_npc_shop()
        logger.log(LOG_LEVEL, f"{self} has reached NPC Shop")
        await self._open_npc_shop()
        await self._activate_equip_tab()
        await self._clear_inventory()
        logger.log(LOG_LEVEL, f"{self} inventory has been cleared")
        await self._close_npc_shop()
        await self._get_to_door_spot()
        logger.log(LOG_LEVEL, f"{self} is back to door (in-town)")
        await self._enter_door()
        logger.log(LOG_LEVEL, f"{self} procedure completed")

    async def _cleanup_with_party_door(self) -> None:
        raise NotImplementedError

    async def _get_to_door_spot(self) -> None:
        # TODO - Implement grid connections
        assert self.data.has_pathing_attributes
        assert self.data.has_minimap_attributes
        door_spot = getattr(
            self.data.current_minimap, "door_spot", [self.data.current_minimap_position]
        )
        target = random.choice(door_spot)
        self._set_fixed_target(target)

        # Overwrite action mechanics to ensure keys are always released
        self.data.create_attribute("action", self._always_release_keys_on_actions)
        await asyncio.to_thread(self._wait_until_target_reached)

    def _wait_until_target_reached(self) -> None:
        while True:
            with self._condition:
                if self._condition.wait_for(
                    lambda: math.dist(
                        self.data.current_minimap_position, self.data.next_target
                    )
                    < self._DISTANCE_TO_DOOR_THRESHOLD,
                    timeout=1.0,
                ):
                    break

    async def _cast_door(self) -> None:
        # TODO - implement validation mechanism to ensure door is properly cast.
        # Use door image from game files and find a matchTemplate threshold acceptable
        # Create a PORTAL connection to (0, 0) and attempt to move there
        grid = self.data.current_minimap.grid

        # Now use current spot as the target
        while True:
            target = self.data.current_minimap_position
            if grid.node(*target).walkable:
                break
            await asyncio.sleep(0.1)
        self._set_fixed_target(target)

        # Add the temporary PORTAL connection
        grid.node(*self.data.next_target).connect(
            grid.node(0, 0), MinimapConnection.PORTAL
        )

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
        door_location = self.data.next_target
        self._set_fixed_target((0, 0))
        await asyncio.to_thread(self._wait_until_minimap_changes)
        await self._setup_new_map(door_location)

    def _wait_until_minimap_changes(self) -> None:
        current_box = self.data.current_entire_minimap_box

        def _predicate():
            self.data.update_attribute("current_entire_minimap_box")
            return current_box != self.data.current_entire_minimap_box

        while True:
            with self._condition:
                if self._condition.wait_for(_predicate, timeout=1.0):
                    self._disable_decision_makers("Rotation")
                    break

    async def _setup_new_map(self, location: tuple[int, int]) -> None:
        # TODO - Compare the new minimap title img to the saved ones to assert in the expected map.
        await asyncio.sleep(1.5)
        # Remove the temporary PORTAL connection
        grid = self.data.current_minimap.grid
        grid.node(*location).connections.pop(-1)
        self.data.current_map = self.data.current_map.path_to_shop
        self.data.update_attribute("current_minimap")
        # This will effectively refresh all minimap attributes
        self._create_minimap_attributes()
        breakpoint()
