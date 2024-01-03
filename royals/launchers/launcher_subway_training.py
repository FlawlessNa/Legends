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
    char1 = royals.models_implementations.characters.Magician

    bot1 = botting.Executor(
        engine=royals.bot_implementations.SubwayTraining,
        ign="FarmFest1",
        client_size="large",
        character_class=char1,
        training_skill="Magic Claw",
    )
    asyncio.run(main(bot1))
