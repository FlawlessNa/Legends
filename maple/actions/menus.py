import multiprocessing.connection
import random
import threading
from typing import Any, Literal

import win32gui

from botting import controller
from botting.core import ActionRequest, ActionWithValidation
from botting.screen import Status, frame_source
from botting.utilities import Box
from maple.screen.minimap import MinimapReader, MinimapState
from maple.screen.stat_window import StatWindowReader

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


CURSOR_SIZE = 64
"""The most room the cursor's image takes right of and below the point it is
drawn from, in client pixels: a Windows cursor is 32 x 32 at 100% scale, and
this leaves room for 200%."""


def point_off(avoid: Box, width: int, height: int) -> tuple[int, int]:
    """
    A random point of a `width` x `height` client area where the cursor, drawn
    from it, covers nothing of `avoid`.

    :raises ValueError: `avoid` leaves no such point.
    """
    left, top = avoid.left - CURSOR_SIZE, avoid.top - CURSOR_SIZE
    candidates = [
        Box(left=0, right=left, top=0, bottom=height - 1) if left >= 0 else None,
        Box(left=avoid.right + 1, right=width - 1, top=0, bottom=height - 1)
        if avoid.right + 1 <= width - 1
        else None,
        Box(left=0, right=width - 1, top=0, bottom=top) if top >= 0 else None,
        Box(left=0, right=width - 1, top=avoid.bottom + 1, bottom=height - 1)
        if avoid.bottom + 1 <= height - 1
        else None,
    ]
    free = [box for box in candidates if box is not None]
    if not free:
        raise ValueError(f"{avoid} leaves no room for the cursor in {width}x{height}")
    return random.choice(free).random()


async def click_then_move_off(
    handle: int,
    target: tuple[int, int],
    avoid: Box,
    nbr_times: int = 1,
    delay: float = 0.15,
) -> None:
    """
    Click `target` `nbr_times`, then move the cursor where it covers nothing of
    `avoid`, so a read of what was clicked isn't hidden by the cursor.
    """
    await controller.mouse_move_and_click(
        handle, target, nbr_times=nbr_times, delay=delay
    )
    _, _, width, height = win32gui.GetClientRect(handle)
    await controller.mouse_move(handle, point_off(avoid, width, height), 0)


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
) -> None:
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
        lambda: minimap_state(minimap, handle) is desired_state,
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
    reader: StatWindowReader,
    condition: threading.Condition,
    timeout: float,
    ensure_displayed: bool = True,
    mode: Literal["Blocking", "Async"] = "Blocking",
    priority: int = ERROR_HANDLING,
) -> None:
    """
    Press the stat window's key until the window is shown (or hidden), judged
    on a fresh capture by `StatWindowReader.shown`: found whole or covered is
    shown; a frame that can't be read is neither, and is checked again.
    """
    request = ActionRequest(
        identifier,
        toggle_ability_menu,
        ign,
        priority,
        block_lower_priority=True,
        args=(handle, ign),
    )

    validated_action = ActionWithValidation(
        pipe,
        lambda: reader.shown(frame_source().grab(handle)) is ensure_displayed,
        condition,
        timeout,
    )

    if mode == "Blocking":
        validated_action.execute_blocking(request)
    elif mode == "Async":
        # Never awaited, so this mode does nothing; no caller uses it.
        validated_action.execute_async(request)  # pyright: ignore[reportUnusedCoroutine]
