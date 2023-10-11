import asyncio
from core.bot import Bot
from core.session_manager import SessionManager


async def main(*bots: Bot) -> None:
    with SessionManager(*bots) as session:
        await session.launch()


if __name__ == '__main__':
    handle = 0x001A05F2
    bot1 = Bot(handle, 'FarmFest1')
    asyncio.run(main(bot1))

