import asyncio
import royals


async def main() -> None:
    with royals.SessionManager() as session:
        bot1 = royals.Bot(handle, "FarmFest1")
        await session.launch()


if __name__ == "__main__":
    handle = 0x001A05F2

    asyncio.run(main())
