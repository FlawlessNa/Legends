import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
from botting import controller, PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from royals.actions import toggle_inventory, expand_inventory, priorities
from royals.constants import (
    INVENTORY_DISCORD_ALERT,
    INVENTORY_CLEANUP_WITH_TOWN_SCROLL,
    INVENTORY_CLEANUP_WITH_SELF_DOOR,
    INVENTORY_CLEANUP_WITH_PARTY_DOOR,
)
from .mixins import MenusMixin

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO


class InventoryManager(MenusMixin, DecisionMaker):
    _throttle = 180

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        cleanup_procedure: int,
        space_left_trigger: int = 96,
        target_tab: str = "Equip",
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe, **kwargs)
        self._condition = DecisionMaker.request_proxy(
            metadata, f"{self}", "Condition"
        )
        self._cleanup_procedure = cleanup_procedure
        self._space_left_trigger = space_left_trigger
        self._target_tab = target_tab

        # Inventory Attributes
        self._create_inventory_menu_attributes()

    async def _decide(self, *args, **kwargs) -> None:
        space_left = await self._check_inventory_space()
        await self._ensure_inventory_displayed(displayed=False)
        if space_left < self._space_left_trigger:
            await self._trigger_procedure()

    async def _check_inventory_space(self) -> int:
        try:
            await self._ensure_inventory_displayed()
            await self._ensure_inventory_extended()
            await self._ensure_on_target_tab()
            return self._get_space_left()
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
                timeout=10.0
            )
        else:
            await self._validate_request_async(
                request,
                lambda: not self.data.inventory_menu.is_displayed(
                    self.data.handle, self.data.current_client_img
                ),
                timeout=10.0
            )
        self.data.update_attribute("inventory_menu_displayed")

    async def _ensure_inventory_extended(self) -> None:
        assert self.data.inventory_menu_displayed

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
            timeout=10.0
        )
        self.data.update_attribute("inventory_menu_extended")

    async def _ensure_on_target_tab(self) -> None:
        assert self.data.inventory_menu_extended

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
            ) == self._target_tab,
            timeout=10.0
        )
        self.data.update_attribute("inventory_menu_active_tab")

    def _get_space_left(self) -> int:
        assert self.data.inventory_menu_active_tab == self._target_tab
        self.data.update_attribute("inventory_space_left")
        return self.data.inventory_space_left

    async def _trigger_procedure(self) -> None:
        if self._cleanup_procedure == INVENTORY_DISCORD_ALERT:
            self.pipe.send(self._discord_alert())
        else:
            self._disable_decision_makers(
                "Rotation",
                "MobsHitting",
                "TelecastMobsHitting",
                "PartyRebuff",
                "SoloRebuff",
            )
            import time
            await asyncio.sleep(10)
            self._enable_decision_makers(
                "Rotation",
                "MobsHitting",
                "TelecastMobsHitting",
                "PartyRebuff",
                "SoloRebuff",
            )
            if self._cleanup_procedure == INVENTORY_CLEANUP_WITH_TOWN_SCROLL:
                await self._cleanup_with_town_scroll()
            elif self._cleanup_procedure == INVENTORY_CLEANUP_WITH_SELF_DOOR:
                await self._cleanup_with_self_door()
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
            )
        )

    async def _cleanup_with_town_scroll(self) -> None:
        raise NotImplementedError

    async def _cleanup_with_self_door(self) -> None:
        pass

    async def _cleanup_with_party_door(self) -> None:
        raise NotImplementedError
