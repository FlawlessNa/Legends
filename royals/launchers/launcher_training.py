"""
Launcher used for single-bot training model.
"""
import asyncio
import botting

from functools import partial

import royals.characters
import royals.engines
import royals.maps


CHARACTER_NAME = "WrongDoor"
CHARACTER_CLASS = royals.characters.Magician
TRAINING_SKILL = "Magic Claw"
TRAINING_MAP = royals.maps.Line1Area1
MOB_COUNT_THRESHOLD = 1
TIME_LIMIT_CENTRAL_TARGET = 5

BUFFS = []

DETECTION_CONFIG_SECTION = "Elephant Cape"
CLIENT_SIZE = "large"

DISABLE_TELEPORT = True

ANTI_DETECTION_MOB_THRESHOLD = 3
ANTI_DETECTION_TIME_THRESHOLD = 10

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
        buffs=BUFFS,
        time_limit=TIME_LIMIT_CENTRAL_TARGET,
        teleport_enabled=not DISABLE_TELEPORT,
        anti_detect_mob_threshold=ANTI_DETECTION_MOB_THRESHOLD,
        anti_detection_time_threshold=ANTI_DETECTION_TIME_THRESHOLD
    )

    bot = botting.Executor(
        engine=royals.engines.TrainingEngine, ign=CHARACTER_NAME, **engine_kwargs
    )
    asyncio.run(main(bot))
