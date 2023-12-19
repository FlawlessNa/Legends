"""
Used to launch any character randomly roaming in one of the Ludi FM maps.
"""
import asyncio
import botting
import royals.bot_implementations


async def main(*bots: botting.Executor) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    bot1 = botting.Executor(
        engine=royals.bot_implementations.SubwayMagicianTraining2, ign="FarmFest1"
    )
    asyncio.run(main(bot1))
