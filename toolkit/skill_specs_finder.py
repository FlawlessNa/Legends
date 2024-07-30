import asyncio
from botting import controller
from botting.utilities import client_handler

from royals import royals_ign_finder

IGN = "FarmFest1"


async def _test_animation_time(handle: int, key: str, cooldown: float) -> None:
    await controller.press(
        handle, key, silenced=True, enforce_delay=False, cooldown=cooldown
    )


if __name__ == "__main__":
    handle = client_handler.get_client_handle(IGN, royals_ign_finder)
    for _ in range(10):
        asyncio.run(_test_animation_time(handle, "c", 0.8))
