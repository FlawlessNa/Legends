import multiprocessing.connection
import random
from typing import Literal

from botting import controller
from botting.core import ActionRequest, ActionWithValidation
from royals.model.interface import Minimap, AbilityMenu
from .priorities import ERROR_HANDLING


async def toggle_menu(
    handle: int,
    ign: str,
    config_name: str,
) -> None:
    await controller.press(
        handle, controller.key_binds(ign)[config_name], silenced=True, delay=0.25
    )


async def toggle_minimap(
    handle: int,
    ign: str,
) -> None:
    await toggle_menu(handle, ign, "Minimap Toggle")


async def toggle_ability_menu(
    handle: int,
    ign: str,
) -> None:
    await toggle_menu(handle, ign, "Ability Menu")


async def expand_inventory(
    handle: int,
    target: tuple[int, int],
    **kwargs
) -> None:
    """
    Must be called after the inventory menu is displayed.
    :param handle:
    :param target:
    :param kwargs:
    :return:
    """
    await controller.mouse_move_and_click(handle, target, nbr_times=1, **kwargs)
    next_target = (
        target[0] + random.randint(-100, 100),
        target[1] - random.randint(50, 100)
    )
    # Simply ensures mouse isn't obstructing the view
    await controller.mouse_move(handle, next_target, total_duration=0)


async def toggle_inventory(
    handle: int,
    ign: str,
) -> None:
    await toggle_menu(handle, ign, "Inventory Menu")


def ensure_minimap_displayed(
    identifier: str,
    handle: int,
    ign: str,
    pipe: multiprocessing.connection.Connection,
    minimap: Minimap,
    condition: multiprocessing.Condition,
    timeout: float,
    desired_state: Literal["Hidden", "Partial", "Full"] = "Full",
    mode: Literal["Blocking", "Async"] = "Blocking",
    priority: int = ERROR_HANDLING,
) -> None:
    request = ActionRequest(
        identifier,
        toggle_minimap,
        ign,
        priority,
        block_lower_priority=True,
        args=(handle, ign),
    )
    validated_action = ActionWithValidation(
        pipe,
        lambda: minimap.get_minimap_state(handle) == desired_state,
        condition,
        timeout,
    )
    if mode == "Blocking":
        validated_action.execute_blocking(request)
    elif mode == "Async":
        validated_action.execute_async(request)


def ensure_ability_menu_displayed(
    identifier: str,
    handle: int,
    ign: str,
    pipe: multiprocessing.connection.Connection,
    menu: AbilityMenu,
    condition: multiprocessing.Condition,
    timeout: float,
    ensure_displayed: bool = True,
    mode: Literal["Blocking", "Async"] = "Blocking",
    priority: int = ERROR_HANDLING,
):
    request = ActionRequest(
        identifier,
        toggle_ability_menu,
        ign,
        priority,
        block_lower_priority=True,
        args=(handle, ign),
    )

    validated_action = ActionWithValidation(
        pipe, lambda: menu.is_displayed(handle) == ensure_displayed, condition, timeout
    )

    if mode == "Blocking":
        validated_action.execute_blocking(request)
    elif mode == "Async":
        validated_action.execute_async(request)
