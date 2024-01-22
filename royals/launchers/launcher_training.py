"""
Launcher used for single-bot training model.
"""
import asyncio
import botting

from functools import partial

import royals.characters
import royals.engines
import royals.maps
import royals.parsers


CHARACTER_NAME = "WrongDoor"
CHARACTER_CLASS = royals.characters.Priest
TRAINING_SKILL = "Heal"
TRAINING_MAP = royals.maps.MysteriousPath3
MOB_COUNT_THRESHOLD = 1
TIME_LIMIT_ON_TARGET = 1

BUFFS = []
NBR_PETS = 3

DETECTION_CONFIG_SECTION = "Elephant Cape"
CLIENT_SIZE = "large"

DISABLE_TELEPORT = False

DISCORD_PARSER = royals.parsers.single_bot_parser

ANTI_DETECTION_MOB_THRESHOLD = 2
ANTI_DETECTION_TIME_THRESHOLD = 15


async def main(*bots: botting.Executor) -> None:
    botting.Executor.update_discord_parser(DISCORD_PARSER)
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
        time_limit=TIME_LIMIT_ON_TARGET,
        teleport_enabled=not DISABLE_TELEPORT,
        anti_detection_mob_threshold=ANTI_DETECTION_MOB_THRESHOLD,
        anti_detection_time_threshold=ANTI_DETECTION_TIME_THRESHOLD,
        num_pets=NBR_PETS
    )

    bot = botting.Executor(
        engine=royals.engines.TrainingEngine,
        ign=CHARACTER_NAME,
        **engine_kwargs
    )
    asyncio.run(main(bot))
