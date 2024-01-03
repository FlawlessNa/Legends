"""
Launcher used for single-bot training model.
"""
import asyncio
import botting

from functools import partial

from royals.characters import Priest
from royals.engines import Training
from royals.maps import MysteriousPath3


async def main(*bots: botting.Executor) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    engine = partial(
        Training,
        ign="FarmFest1",
        client_size="large",
        character_detection='Elephant Cape',
        character_class=Priest,
        map=MysteriousPath3,
        training_skill="Heal"
    )

    bot = botting.Executor(
        engine=engine,
        ign="FarmFest1",
    )
    asyncio.run(main(bot))
