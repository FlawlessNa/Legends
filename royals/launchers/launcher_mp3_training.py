"""
Used to launch cleric training at mp3.
"""
import asyncio
import botting
import royals.bot_implementations
import royals.models_implementations


async def main(*bots: botting.Executor) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    char1 = royals.models_implementations.characters.Cleric

    bot1 = botting.Executor(
        engine=royals.bot_implementations.MysteriousPath3Training,
        ign="FarmFest1",
        client_size="large",
        section='Podium Effect',
        character_class=char1,
        training_skill="Heal"
    )
    asyncio.run(main(bot1))
