import asyncio
import botting
import royals


async def main(*bots: botting.Bot) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    handle = 0x002E05E6
    data = royals.RoyalsData(handle, "FarmFest1")

    bot1 = botting.Bot(handle, "FarmFest1", data, monitor=royals.TestBot)
    asyncio.run(main(bot1))
