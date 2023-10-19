import asyncio
import royals
from royals.bot_implementations.test_bot import TestBot


async def main(*bots: royals.Bot) -> None:
    with royals.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    handle = 0x001A05F2
    bot1 = TestBot(handle, "FarmFest1")
    asyncio.run(main(bot1))
