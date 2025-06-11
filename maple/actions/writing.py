import asyncio
from botting import controller


async def write_in_chat(
    handle: int,
    message: str,
    channel: str = "general",
    whisper_to: str | None = None,
    silenced: bool = False,
    **kwargs,
) -> None:
    mapping = {  # TODO - Change these to configs
        "general": "1",
        "party": "2",
        "buddy": "3",
        "guild": "4",
        "alliance": "5",
        "spouse": "6",
        "whisper": "h",
    }
    if channel not in mapping:
        raise ValueError(f"Channel {channel} not recognized.")
    key = mapping[channel]

    await controller.press(handle, key, silenced=silenced)
    await asyncio.sleep(0.5)

    if channel == "whisper":
        if whisper_to is not None:
            await controller.write(handle, whisper_to, silenced=silenced, **kwargs)
            await asyncio.sleep(0.25)
        await controller.press(handle, "enter", silenced=silenced)
        await asyncio.sleep(0.25)

    await controller.write(handle, message, silenced=silenced, **kwargs)
    await asyncio.sleep(0.25)
    await controller.press(handle, "enter", silenced=silenced)
    await asyncio.sleep(0.25)
    await controller.press(handle, "enter", silenced=silenced)
