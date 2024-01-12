"""
Launcher used for multi-bot Leeching model.
A leecher bot is the primary process here, but "buffers" engines can be added to
better control party buffs.
"""
import asyncio
import botting

from functools import partial

import royals.characters
import royals.engines
import royals.maps


CHARACTER_NAME = "FarmFest1"
LEECHERS_NAMES = ["FarmFest2", "FarmFest3", "FarmFest4", "FarmFest5", "LootFest"]
CHARACTER_CLASS = royals.characters.Bishop
LEECHERS_CLASSES = [royals.characters.Magician] * 4 + [royals.characters.Rogue]
TRAINING_MAP = royals.maps.PathOfTime1
MOB_COUNT_THRESHOLD = 5

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
        mob_count_threshold=MOB_COUNT_THRESHOLD,
    )

    bot = botting.Executor(engine=royals.engines.LeechingEngine, ign=CHARACTER_NAME, **engine_kwargs)
    # leechers = [
    #     botting.Executor(engine=royals.engines.Leecher, ign=name, **{"character": char})
    #     for name, char in zip(LEECHERS_NAMES, LEECHERS_CLASSES)
    # ]
    asyncio.run(main(bot))
