"""
Launcher used for multi-bot Leeching model.
A leecher bot is the primary process here, but "Mule Buffers" engines can be added to
better control party buffs as well as automatically distribute AP upon level up.
"""

import asyncio
import multiprocessing

from functools import partial

import botting
import royals.parsers


LEECHER_IGN = "WrongDoor"
LEECHER_CLASS = royals.characters.Bishop
LEECHER_BUFFS_TO_USE = ["Magic Guard", "Invincible"]
LEECHER_NUM_PETS = 3
BUFFS_TO_SYNCHRONIZE = ["Holy Symbol", "Maple Warrior", "Haste"]

BUFF_MULES_IGN = ["UluLoot", "BCoinFarm", "iYieldMoney", "MoneyEngine", "FinancialWiz"]
BUFF_MULES_CLASSES = [royals.characters.Hermit] + [royals.characters.Magician] * 4

NUM_BOTS = 6
TRAINING_MAP = royals.maps.FantasyThemePark1
MOB_COUNT_THRESHOLD = 6

DETECTION_CONFIG_SECTION = "Elephant Cape"
CLIENT_SIZE = "large"

ANTI_DETECTION_MOB_THRESHOLD = 4
ANTI_DETECTION_TIME_THRESHOLD = 10

DISCORD_PARSER = royals.parsers.single_bot_parser  # TODO - Change to multi_bot_parser


async def main(*bots: botting.Executor) -> None:
    botting.Executor.update_discord_parser(DISCORD_PARSER)
    with botting.SessionManager(*bots) as session:
        await session.start()


if __name__ == "__main__":
    notifier = multiprocessing.Event()
    barrier = multiprocessing.Barrier(NUM_BOTS, timeout=5)
    counter = multiprocessing.BoundedSemaphore(NUM_BOTS)
    leecher_char = partial(
        LEECHER_CLASS,
        LEECHER_IGN,
        detection_configs=DETECTION_CONFIG_SECTION,
        client_size=CLIENT_SIZE,
    )
    leecher_engine_kwargs = dict(
        game_map=TRAINING_MAP(),
        character=leecher_char,
        mob_count_threshold=MOB_COUNT_THRESHOLD,
        notifier=notifier,
        barrier=barrier,
        counter=counter,
        buffs=LEECHER_BUFFS_TO_USE,
        synchronized_buffs=BUFFS_TO_SYNCHRONIZE,
        anti_detection_mob_threshold=ANTI_DETECTION_MOB_THRESHOLD,
        anti_detection_time_threshold=ANTI_DETECTION_TIME_THRESHOLD,
        num_pets=LEECHER_NUM_PETS,
    )
    leecher = botting.Executor(
        engine=royals.engines.LeechingEngine, ign=LEECHER_IGN, **leecher_engine_kwargs
    )

    mules_char = [
        partial(class_, ign, DETECTION_CONFIG_SECTION, CLIENT_SIZE)
        for class_, ign in zip(BUFF_MULES_CLASSES, BUFF_MULES_IGN)
    ]
    mules_engine_kwargs = [
        dict(
            game_map=TRAINING_MAP,
            character=char,
            notifier=notifier,
            barrier=barrier,
            counter=counter,
            synchronized_buffs=BUFFS_TO_SYNCHRONIZE,
        )
        for char in mules_char
    ]
    mules = [
        botting.Executor(engine=royals.engines.BuffMule, ign=name, **kwargs)
        for name, kwargs in zip(BUFF_MULES_IGN, mules_engine_kwargs)
    ]

    asyncio.run(main(leecher, *mules))
