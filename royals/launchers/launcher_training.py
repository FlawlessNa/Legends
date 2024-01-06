"""
Launcher used for single-bot training model.
"""
import asyncio
import botting

from functools import partial

from royals.characters import Priest
from royals.engines import TrainingEngine
from royals.maps import EncounterWithTheBuddha, MysteriousPath3


CHARACTER_NAME = "FarmFest1"
CHARACTER_CLASS = Priest
TRAINING_SKILL = "Shining Ray"
TRAINING_MAP = MysteriousPath3
MOB_COUNT_THRESHOLD = 4
TIME_LIMIT_CENTRAL_TARGET = 60

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
        buffs=["Invincible", "Magic Guard", "Bless"],
        time_limit=TIME_LIMIT_CENTRAL_TARGET,
    )

    bot = botting.Executor(engine=TrainingEngine, ign=CHARACTER_NAME, **engine_kwargs)
    asyncio.run(main(bot))
