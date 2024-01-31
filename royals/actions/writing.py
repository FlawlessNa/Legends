import asyncio
from botting.core import controller


async def write_in_chat(
    handle: int,
    message: str,
    channel: str = "general",
    whisper_to: str | None = None,
    silenced: bool = True,
    **kwargs,
) -> None:
    mapping = {
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


async def random_chat_response(handle: int, msg: str, silenced: bool = True):
    """
    Selects a random response from a list and writes it in general chat.
    :param handle:
    :param msg:
    :param silenced:
    :return:
    """
    await write_in_chat(handle, msg, silenced=silenced)
