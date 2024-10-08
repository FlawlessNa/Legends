import asyncio
from botting.core.session_manager import SessionManager
import royals.bots as bots
import royals.model.maps as maps
import royals.parsers

training_configs = {
    "num_pets": 1,
    "game_map": maps.MysteriousPath3,
    "mob_count_threshold": 1,
    "included_buffs": ["Invincible"],
    "training_skill": "Heal",
    "models_path": {
        "All": "data/model_runs/character_detection/ChronosAndMp3WithCharacter - Nano"
    },
    "smart_rotation_enabled": True,
    # "disable_teleport": True,
    "mob_spawn_alert_timer": 15,
    "mob_spawn_alert_threshold": 5,
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
