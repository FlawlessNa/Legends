import multiprocessing.connection
import random
import threading
from typing import Any, Literal

from botting import controller
from botting.core import ActionRequest, ActionWithValidation
from botting.screen import Status, frame_source
from maple.model.interface import AbilityMenu
from maple.screen.minimap import MinimapReader, MinimapState

from .priorities import ERROR_HANDLING


async def toggle_menu(
    handle: int,
    ign: str,
    config_name: str,
) -> None:
    await controller.press(
        handle, controller.key_binds(ign)[config_name], silenced=False, delay=0.3
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


async def expand_inventory(handle: int, target: tuple[int, int], **kwargs: Any) -> None:  # noqa: ANN401
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
        target[1] - random.randint(50, 100),
    )
    # Simply ensures mouse isn't obstructing the view
    await controller.mouse_move(handle, next_target, total_duration=0)


async def toggle_inventory(
    handle: int,
    ign: str,
) -> None:
    await toggle_menu(handle, ign, "Inventory Menu")


def minimap_state(minimap: MinimapReader, handle: int) -> MinimapState | None:
    """
    The minimap's state in a fresh capture of the client: `ABSENT` when it isn't
    found at all, and `None` when that can't be told (covered, or the frame
    unusable).
    """
    reading = minimap.read(frame_source().grab(handle))
    if reading.value is not None:
        return reading.value.state
    if reading.status is Status.ABSENT:
        return MinimapState.ABSENT
    return None


def minimap_banner_shown(minimap: MinimapReader, handle: int) -> bool:
    """Whether a fresh capture of the client shows the minimap expanded with its
    banner, which draws the map's title."""
    reading = minimap.read(frame_source().grab(handle))
    return reading.value is not None and reading.value.banner is not None


def ensure_minimap_displayed(
    identifier: str,
    handle: int,
    ign: str,
    pipe: multiprocessing.connection.Connection,
    minimap: MinimapReader,
    condition: threading.Condition,
    timeout: float,
    desired_state: MinimapState = MinimapState.EXPANDED,
    mode: Literal["Blocking", "Async"] = "Blocking",
    priority: int = ERROR_HANDLING,
    banner: bool = False,
) -> None:
    """
    Presses the minimap key until the minimap is in `desired_state`, and, with
    `banner`, expanded with its banner (`MaxMap`).

    :raises TimeoutError: It isn't, after `timeout` seconds or 10 presses.
    """
    request = ActionRequest(
        identifier,
        toggle_minimap,
        ign,
        priority,
        block_lower_priority=True,
        args=(handle, ign),
        cancels_itself=True,
    )
    validated_action = ActionWithValidation(
        pipe,
        (
            (lambda: minimap_banner_shown(minimap, handle))
            if banner
            else (lambda: minimap_state(minimap, handle) is desired_state)
        ),
        condition,
        timeout,
    )
    if mode == "Blocking":
        validated_action.execute_blocking(request)
    elif mode == "Async":
        # Never awaited, so this mode does nothing; no caller uses it.
        validated_action.execute_async(request)  # pyright: ignore[reportUnusedCoroutine]


def ensure_ability_menu_displayed(
    identifier: str,
    handle: int,
    ign: str,
    pipe: multiprocessing.connection.Connection,
    menu: AbilityMenu,
    condition: threading.Condition,
    timeout: float,
    ensure_displayed: bool = True,
    mode: Literal["Blocking", "Async"] = "Blocking",
    priority: int = ERROR_HANDLING,
) -> None:
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
        # Never awaited, so this mode does nothing; no caller uses it.
        validated_action.execute_async(request)  # pyright: ignore[reportUnusedCoroutine]
