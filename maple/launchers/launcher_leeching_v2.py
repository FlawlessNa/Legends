"""
Multi-client leeching setup: one leecher clearing the map, five mules riding
along for the party buffs and the loot.

This is the maintainer's own tracked setup. For your own characters, prefer a
profile instead of editing this file:

    python -m maple.launchers.run <profile>

See docs/FIRST_BOT.md. A profile supports mules too, so this whole layout can
be expressed as one YAML file under profiles/.

The map's JSON config (configs/maps/) must define `party_rebuff_zone` for
PartyRebuff to know where the party gathers; alternatively, pass an explicit
`buff_location` in the configs below.
"""

import asyncio

import maple.parsers
from botting.core.session_manager import SessionManager
from maple import bots

SYNCHRONIZED_BUFFS = ["Holy Symbol", "Maple Warrior", "Haste", "Meso Up"]
GAME_MAP = "Line1Area1"
CLIENT_SIZE = "large"
DETECTION_CONFIG_SECTION = "Elephant Cape"

leeching_configs = {
    "num_pets": 3,
    "game_map": GAME_MAP,
    "mob_count_threshold": 8,
    "detection_configs": DETECTION_CONFIG_SECTION,
    "client_size": CLIENT_SIZE,
    "models_path": {"All": "data/models/production/global"},
    "mob_spawn_alert_timer": 15,
    "mob_spawn_alert_threshold": 4,
    "included_buffs": ["Invincible", "Magic Guard"],
    "synchronized_buffs": SYNCHRONIZED_BUFFS,
}
mule_configs = {
    "synchronized_buffs": SYNCHRONIZED_BUFFS,
    "game_map": GAME_MAP,
    "client_size": CLIENT_SIZE,
    "detection_configs": DETECTION_CONFIG_SECTION,
    "skills_to_reset": ["Haste", "Meso Up"],
}


async def main() -> None:
    with SessionManager(maple.parsers.MapleParser) as session:
        leecher = bots.LeechingBot("Farmacy", session.metadata, **leeching_configs)
        mule1 = bots.LeechMuleWithBuffs(
            "UluLoot", session.metadata, character_class="Hermit", **mule_configs
        )
        mule2 = bots.LeechMuleWithoutBuffs(
            "FinancialWiz", session.metadata, **mule_configs
        )
        mule3 = bots.LeechMuleWithoutBuffs(
            "MoneyEngine", session.metadata, **mule_configs
        )
        mule4 = bots.LeechMuleWithoutBuffs(
            "iYieldMoney", session.metadata, **mule_configs
        )
        mule5 = bots.LeechMuleWithoutBuffs(
            "BCoinFarm", session.metadata, **mule_configs
        )
        await session.launch([leecher], [mule1, mule2, mule3, mule4, mule5])


if __name__ == "__main__":
    asyncio.run(main(), debug=True)
