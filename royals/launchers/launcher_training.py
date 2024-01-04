"""
Launcher used for single-bot training model.
"""
import asyncio
import botting

from functools import partial

from royals.characters import Priest
from royals.engines import TrainingEngine
from royals.maps import MysteriousPath3


CHARACTER_NAME = "FarmFest1"
CHARACTER_CLASS = Priest
TRAINING_SKILL = "Heal"
TRAINING_MAP = MysteriousPath3
MOB_COUNT_THRESHOLD = 3

DETECTION_CONFIG_SECTION = "Elephant Cape"
CLIENT_SIZE = "large"


async def main(*bots: botting.Executor) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    character = partial(
        CHARACTER_CLASS,
        CHARACTER_NAME,
        detection_configs=DETECTION_CONFIG_SECTION,
        client_size=CLIENT_SIZE,
    )
    engine_kwargs = dict(
        character=character,
        game_map=TRAINING_MAP,
        training_skill=TRAINING_SKILL,
        mob_count_threshold=MOB_COUNT_THRESHOLD,
        buffs=["Invincible"],
    )

    bot = botting.Executor(engine=TrainingEngine, ign=CHARACTER_NAME, **engine_kwargs)
    asyncio.run(main(bot))
