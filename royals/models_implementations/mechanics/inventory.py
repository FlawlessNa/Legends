from botting.core import QueueAction


class InventoryChecks:
    """
    Utility class for InventoryManager.
    Defines all methods used for inventory management.
    """
    def _ensure_is_displayed(self) -> QueueAction | None:
        pass

    def _ensure_is_extended(self) -> QueueAction | None:
        pass

    def _ensure_proper_tab(self) -> QueueAction | None:
        pass

    def _get_space_left(self) -> int:
        pass

    def _use_mystic_door(self) -> QueueAction | None:
        pass

    def _move_to_door(self, target: tuple[int, int]) -> QueueAction | None:
        pass

    def _enter_door(self, target: tuple[int, int]) -> QueueAction | None:
        pass

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
    pass