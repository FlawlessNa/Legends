import asyncio
import botting
from royals.bot_implementations import TestBot


async def main(*bots: botting.Bot) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    handle = 0x00620DFE
    data = royals.GameData(handle, "FarmFest1")

    bot1 = royals.Bot(handle, "FarmFest1", data, monitor=TestBot)
    asyncio.run(main(bot1))
