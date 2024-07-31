import asyncio
from botting.core.session_manager import SessionManager
import royals.bots as bots
import royals.model.maps as maps
import royals.parsers

leeching_configs = {
    "self_buffs": [],
    "num_pets": 3,
    "game_map": maps.FantasyThemePark1,
    "mob_count_threshold": 6,
    "detection_configs": "Elephant Cape",
    "client_size": "large",
    "anti_detection_mob_threshold": 4,
    "anti_detection_time_threshold": 10,
}


async def main():
    with SessionManager(royals.parsers.RoyalsParser) as session:
        leecher = bots.LeechingBot("WrongDoor", session.metadata, **leeching_configs)
        # mule1 = bots.TestBot('UluLoot', session.metadata)
        # mule2 = bots.TestBot('FinancialWiz', session.metadata)
        # mule3 = bots.TestBot('MoneyEngine', session.metadata)
        # mule4 = bots.TestBot('iYieldMoney', session.metadata)
        # mule5 = bots.TestBot('BCoinFarm', session.metadata)
        # await session.launch([leecher], [mule1, mule2, mule3, mule4, mule5])
        await session.launch([leecher])


if __name__ == "__main__":
    asyncio.run(main())
