import asyncio
from botting.core.session_manager import SessionManager
import maple.bots as bots
import maple.parsers

training_configs = {
    "num_pets": 1,
    "game_map": "GhostShip1",
    "open_minimap_editor": False,
    "mob_count_threshold": 1,
    "included_buffs": ["Invincible", "Holy Symbol"],
    "training_skill": "Heal",
    "models_path": {"All": "data/models/production/global"},
    "smart_rotation_enabled": False,
    # "disable_teleport": True,
    "mob_spawn_alert_timer": 15,
    "mob_spawn_alert_threshold": 4,
    # 'speed_multiplier': 1.4,
    # 'jump_multiplier': 1.23,
    # "detection_configs": "Elephant Cape"
}


async def main():
    with SessionManager(maple.parsers.MapleParser) as session:
        leecher = bots.TrainingBot("StarBase", session.metadata, **training_configs)
        # mule1 = bots.TestBot('UluLoot', session.metadata)
        # mule2 = bots.TestBot('FinancialWiz', session.metadata)
        # mule3 = bots.TestBot('MoneyEngine', session.metadata)
        # mule4 = bots.TestBot('iYieldMoney', session.metadata)
        # mule5 = bots.TestBot('BCoinFarm', session.metadata)
        # await session.launch([leecher], [mule1, mule2, mule3, mule4, mule5])
        await session.launch([leecher])


if __name__ == "__main__":
    asyncio.run(main())
