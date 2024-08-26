import asyncio
from botting.core.session_manager import SessionManager
import royals.bots as bots
import royals.model.maps as maps
import royals.parsers


SYNCHRONIZED_BUFFS = ["Holy Symbol", "Maple Warrior", "Haste", "Meso Up"]
GAME_MAP = maps.FantasyThemePark1
CLIENT_SIZE = "large"
DETECTION_CONFIG_SECTION = "Elephant Cape"

leeching_configs = {
    "num_pets": 3,
    "game_map": GAME_MAP,
    "mob_count_threshold": 6,
    "detection_configs": DETECTION_CONFIG_SECTION,
    "client_size": CLIENT_SIZE,
    "anti_detection_mob_threshold": 4,
    "anti_detection_time_threshold": 10,
    "included_buffs": ["Invincible"],
    "synchronized_buffs": SYNCHRONIZED_BUFFS,
}
mule_configs = {
    "synchronized_buffs": SYNCHRONIZED_BUFFS,
    "game_map": GAME_MAP,
    "client_size": CLIENT_SIZE,
    "detection_configs": DETECTION_CONFIG_SECTION,
}


async def main():
    with SessionManager(royals.parsers.RoyalsParser) as session:
        leecher = bots.LeechingBot("WrongDoor", session.metadata, **leeching_configs)
        mule1 = bots.LeechMuleWithBuffs(
            "UluLoot", session.metadata, character_class="Hermit", **mule_configs
        )
        # mule2 = bots.TestBot('FinancialWiz', session.metadata)
        # mule3 = bots.TestBot('MoneyEngine', session.metadata)
        # mule4 = bots.TestBot('iYieldMoney', session.metadata)
        # mule5 = bots.TestBot('BCoinFarm', session.metadata)
        # await session.launch([leecher], [mule1, mule2, mule3, mule4, mule5])
        await session.launch([leecher], [mule1])


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
