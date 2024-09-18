import asyncio
from botting.core.session_manager import SessionManager
import royals.bots as bots
import royals.model.maps as maps
import royals.parsers

training_configs = {
    "num_pets": 1,
    "game_map": maps.PathOfTime1,
    "mob_count_threshold": 1,
    "included_buffs": [],
    "training_skill": "Heal",
    "model_path": "data/model_runs/character_detection/ClericChronosTraining - Nano120",
    "smart_rotation_enabled": True,
    # "disable_teleport": True,
    "mob_spawn_alert_timer": 10,
    "mob_spawn_alert_threshold": 3,
}


async def main():
    with SessionManager(royals.parsers.RoyalsParser) as session:
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
