import multiprocessing.connection
from typing import Literal

from botting import controller
from botting.core import ActionRequest, ActionWithValidation
from royals.model.interface import Minimap
from ._priorities import ERROR_HANDLING


async def toggle_menu(
    handle: int,
    ign: str,
    config_name: str,
) -> None:
    await controller.press(
        handle, controller.key_binds(ign)[config_name], silenced=True, delay=0.1
    )


async def toggle_minimap(
    handle: int,
    ign: str,
) -> None:
    await toggle_menu(handle, ign, "Minimap Toggle")


def minimap_display_validator(
    minimap: Minimap, handle: int, desired_state: str
):
    return minimap.get_minimap_state(handle) == desired_state


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
) -> None:

    request = ActionRequest(
        identifier,
        toggle_minimap,
        ign,
        ERROR_HANDLING,
        block_lower_priority=True,
        args=(handle, ign),
    )
    validated_action = ActionWithValidation(
        pipe,
        lambda: minimap_display_validator(minimap, handle, desired_state),
        condition,
        timeout,
    )
    if mode == "Blocking":
        validated_action.execute_blocking(request)
    elif mode == "Async":
        validated_action.execute_async(request)
